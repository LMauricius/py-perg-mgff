"""The pushdown machine a highlighting backend spells.

Kate's contexts and TextMate's `begin`/`end` patterns are the same machine over
text: a stack of states, each an ordered list of rules, where a rule may colour
what it matched, push a state, pop back, or stay. The machine is therefore
derived once here, format-independently; `kate` and `textmate` only spell it.

    Machine                       Kate                    TextMate
    ------------------------------------------------------------------------
    Context                       <context>               a repository entry
    Context.styles               attribute=              contentName
    Context.line_end              lineEndContext=         while
    ContextRule.push              context="X"             begin + patterns
    ContextRule.pop               context="#pop"          the end expression
    ContextRule.region            beginRegion/endRegion   the bracket pair

What the backends could not ask before is **what may appear where**. A context
holds the rules its position in the grammar reaches and nothing else, so a
marker is a keyword only where a line may begin with one, a subgroup holds no
definitions because nothing spelling one is reachable from it, and a comment
stays a comment across the lines its group spans.

**A state is a place a line may begin.** `split` reads a rule tree as "what may
appear on this line" and "what is left for the next one", the states are the
distinct leftovers, and a line break moves between them. That is what carries a
definition on to its alternative lines without a lookahead the grammar cannot
spell: the leftover after the first line is a state of its own, and a line
matching nothing in it pops the whole chain so the scope below reads the line
from its first character.

A newline is never matched by a rule — a line is all a highlighter sees at once
— so a `\\n` written in a `Parse` rule shapes the machine instead of being
matched by it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ...diagnostics.errors import GeneratorError
from ...diagnostics.span import Position, Span
from ...mgff.common.characters import CHARACTER, CHARACTER_SET
from ...mgff.common.rules import Choice, MacroCall, Reference, Repetition, Rule, Sequence
from ...mgff.lexing.cst import Item, Text
from ...mgff.semantics.model import Production, Target
from .styles import styles_of
from .naming import NameAllocator, safe_identifier
from .regex import regex_of
from .walk import flatten, fuse_literals, nullable, single_character, walk

#: The macro a target starts at.
START_PRODUCTION = "File"

#: What a production becomes in the machine.
SPAN = "span"  # a context of its own
TOKEN = "token"  # one rule, coloured by its styles
INLINE = "inline"  # transparent: its parts belong to whoever reached it

#: What `Context.line_end` may say besides the name of a context.
STAY = "#stay"
POP = "#pop"

#: How long a chain of line contexts may grow before the rule that spells it is
#: called endless. A role carrying on to a further line leaves a state behind,
#: and a rule leaving *more* behind on every line — `d B = \n B a` — has no
#: machine at all, since the states never repeat.
MAX_LINE_STATES = 64


# -- the model -------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Match:
    """How a rule recognises text.

    The rule tree is handed over unspelled: Kate picks the cheapest of its dozen
    rule kinds and TextMate has only an expression, and neither decision belongs
    here. `look_ahead` matches without consuming, which is how a chained line
    context leaves without eating text the context below it must still read.
    """

    rule: Rule
    look_ahead: bool = False
    #: Whether the match may only fire between word boundaries. A marker
    #: spelled as a letter — `d`, `t`, `p` — must not open a line inside a
    #: word, and nothing else in the machine cares where a word begins.
    word_boundary: bool = False


@dataclass(slots=True)
class ContextRule:
    """One rule of a context: what it matches, how it is coloured, where it goes.

    `pop` counts the contexts to leave, so a chain of line contexts returns to
    the scope it was entered from in one step.
    """

    match: Match
    styles: list[str] = field(default_factory=list)
    push: str | None = None
    pop: int = 0
    region: str | None = None


@dataclass(slots=True)
class Context:
    """One state of the machine: a place a line may begin, and its rules.

    `styles` colour whatever the context holds that no rule of its own claims,
    which is how a comment colours its body rather than only its `#`.
    """

    name: str
    styles: list[str] = field(default_factory=list)
    rules: list[ContextRule] = field(default_factory=list)
    line_end: str = STAY
    #: The production this context came from, for folding regions and messages.
    origin: str = ""


@dataclass(slots=True)
class Machine:
    """Every context, and the one a document starts in."""

    contexts: dict[str, Context] = field(default_factory=dict)
    start: str = START_PRODUCTION


# -- reading a rule tree ---------------------------------------------------

#: A rule matching nothing at all, which is what is left of a line after its
#: newline has been read.
EMPTY = Sequence([])


def is_newline(node: Rule) -> bool:
    """Whether a node matches exactly one newline."""
    return single_character(node) == "\n"


def key_of(node: Rule | None) -> str:
    """A stable key for a rule tree, so two states that are alike are one state."""
    return "" if node is None else repr(node)


def parts_of(node: Rule) -> list[Rule]:
    """A node's top-level parts, sequences merged and literal runs fused."""
    return fuse_literals(flatten(node))


# -- splitting a rule at its line breaks -----------------------------------

@dataclass(slots=True)
class Line:
    """What a rule contributes to the line it starts on.

    `parts` is everything that may be matched before the line ends — a set, not
    a sequence, because a context tries its rules at every position and does not
    care in which order they were reached. `leftovers` is what each line break
    inside the rule leaves for the next line, and `finishes` says whether the
    rule may be done before any line break, which is what lets the context that
    reached it carry on.

    Reading a rule this way is what keeps the walk linear: a sequence unions its
    head's parts with its tail's rather than enumerating every way the two could
    be divided between lines.
    """

    parts: list[Rule] = field(default_factory=list)
    leftovers: list[Rule] = field(default_factory=list)
    finishes: bool = True


class Splitter:
    """Reads rule trees as lines: what appears now, and what is left over.

    A reference is followed only when the production it names is transparent —
    a span or a token is a part in its own right, and stops the walk. Results
    are cached, since a grammar reaches the same subtree many times.
    """

    def __init__(self, classify) -> None:
        self.classify = classify
        self.cache: dict[str, Line] = {}

    def read(self, node: Rule) -> Line:
        """What a node puts on this line, and what it leaves for the next."""
        key = key_of(node)
        found = self.cache.get(key)
        if found is None:
            self.cache[key] = found = self._read(node, seen=frozenset())
        return found

    # -- the walk ----------------------------------------------------------

    def _read(self, node: Rule, seen: frozenset[str]) -> Line:
        if is_newline(node):
            # The line ends here, and nothing of this node is left over.
            return Line(leftovers=[EMPTY], finishes=False)
        if not self.crosses_line(node) and self.atomic(node):
            return Line(parts=[node])
        if isinstance(node, Sequence):
            return self._read_sequence(list(node.items), seen)
        if isinstance(node, Choice):
            return self._merge([self._read(option, seen) for option in node.options])
        if isinstance(node, Repetition):
            return self._read_repetition(node, seen)
        if isinstance(node, Reference):
            return self._read_reference(node, seen)
        return Line(parts=[node])

    def _read_sequence(self, items: list[Rule], seen: frozenset[str]) -> Line:
        """The head's line, plus the tail's when the head may end on this one."""
        if not items:
            return Line()
        head, rest = items[0], items[1:]
        first = self._read(head, seen)
        # Whatever the head left over is followed by the rest of the sequence.
        line = Line(
            parts=list(first.parts),
            leftovers=[_sequence([left, *rest]) for left in first.leftovers],
            finishes=False,
        )
        if first.finishes:
            following = self._read_sequence(rest, seen)
            _extend(line.parts, following.parts)
            _extend(line.leftovers, following.leftovers)
            line.finishes = following.finishes
        return line

    def _read_repetition(self, node: Repetition, seen: frozenset[str]) -> Line:
        """A repetition may stop before this line ends, or carry on past it.

        A further iteration adds the parts this one already did, so the union is
        the same; only the leftovers gain the repetition itself.
        """
        body = self._read(node.body, seen)
        return Line(
            parts=list(body.parts),
            leftovers=[_sequence([left, _looping(node)]) for left in body.leftovers],
            finishes=node.minimum == 0 or body.finishes,
        )

    def _read_reference(self, node: Reference, seen: frozenset[str]) -> Line:
        """A transparent production is walked into; anything else is a part."""
        production = self.classify.production(node.name)
        if production is None or self.classify.of(production) != INLINE:
            return Line(parts=[node])
        if node.name in seen:
            # A cycle through transparent macros: whatever it would contribute
            # is already being collected by the walk that reached it.
            return Line()
        return self._read(production.rule, seen | {node.name})

    # -- helpers -----------------------------------------------------------

    def _merge(self, lines: list[Line]) -> Line:
        """The union of several readings, as a choice between them is."""
        merged = Line(finishes=False)
        for line in lines:
            _extend(merged.parts, line.parts)
            _extend(merged.leftovers, line.leftovers)
            merged.finishes = merged.finishes or line.finishes
        return merged

    def atomic(self, node: Rule, seen: frozenset[str] = frozenset()) -> bool:
        """Whether a node is one rule's worth of matching.

        A subtree naming no span and no token of its own is matched by a single
        expression, which is both cheaper and more readable than one rule per
        character it could match.

        A production already on the path reaches itself, and an expression does
        not recurse, so the answer there is no — the same answer `is_regular`
        gives, and what stops the walk on a recursive grammar.
        """
        for found in walk(node):
            if isinstance(found, Reference):
                if found.name in seen:
                    return False
                production = self.classify.production(found.name)
                if production is None or self.classify.of(production) != INLINE:
                    return False
                if not self.atomic(production.rule, seen | {found.name}):
                    return False
        return True

    def crosses_line(self, node: Rule) -> bool:
        """Whether a node can reach a newline; the classifier knows how to tell."""
        return self.classify.crosses_line(node)

def _extend(into: list[Rule], more: list[Rule]) -> None:
    """Add what is not there yet, keeping the order things were found in."""
    known = {key_of(node) for node in into}
    for node in more:
        if key_of(node) not in known:
            known.add(key_of(node))
            into.append(node)


def _sequence(items: list[Rule]) -> Rule:
    """A sequence of the items, unwrapped when there is only one."""
    items = [item for item in items if item is not EMPTY and item != EMPTY]
    if not items:
        return EMPTY
    return items[0] if len(items) == 1 else Sequence(items)


def _looping(node: Repetition) -> Repetition:
    """The same repetition, with any minimum already satisfied."""
    return Repetition(node.body, 0, node.maximum, node.marker)


# -- classifying productions -----------------------------------------------


#: A fixed character that opens or closes a span, and the styles it carries.
#: A marker written as a macro of its own — `d DefMarker = d > style(Keyword)` —
#: keeps its style here while the context it opens keeps another, which is how a
#: keyword opens a span whose body is not a keyword.
Terminal = tuple[str, list[str]]


class Classifier:
    """Says what each production of a target is, and remembers the answer.

    The answers depend on each other — asking what a production is asks what the
    productions it reaches are, itself among them — so they are settled together
    rather than one at a time. Answering the first question classifies every
    production, starting from "all transparent" and recomputing until nothing
    changes. A classification read off a fixpoint is the same whichever
    production was asked about first; one computed while another was still being
    answered would not be.
    """

    def __init__(self, target: Target) -> None:
        self.target = target
        self.answers: dict[str, str] = {}
        #: True while the fixpoint is being computed, so the recomputation reads
        #: the round's answers instead of starting a round of its own.
        self.settling = False

    def production(self, name: str) -> Production | None:
        """One production of the target by name."""
        return self.target.productions.get(name)

    def of(self, production: Production) -> str:
        """Whether a production is a span, a token or transparent."""
        if production.name not in self.answers and not self.settling:
            self._settle()
        return self.answers.get(production.name, INLINE)

    def _settle(self) -> None:
        """Classify every production, iterating until the answers stop moving.

        The rounds are bounded by the number of productions, which no chain of
        answers depending on answers can outrun, and the last round is the one
        that finds nothing left to change.
        """
        self.settling = True
        try:
            self.answers = {name: INLINE for name in self.target.productions}
            for _ in range(len(self.target.productions) + 1):
                found = {
                    name: self._classify(production)
                    for name, production in self.target.productions.items()
                }
                if found == self.answers:
                    break
                self.answers = found
        finally:
            self.settling = False

    def _classify(self, production: Production) -> str:
        if self.brackets_of(production) or self.line_openings_of(production):
            return SPAN
        # A production nothing would colour is no rule of its own: whatever
        # reached it colours it, which is what keeps whitespace and punctuation
        # out of the contexts as rules.
        if styles_of(production) not in ([], ["Normal"]) and self.is_regular(production):
            return TOKEN
        return INLINE

    def is_regular(self, production: Production) -> bool:
        """Whether one expression can match the production.

        A production that reaches itself cannot be a token: a rule matches with
        an expression, and an expression does not recurse. It is transparent
        instead, and whatever it holds is read where it was reached.
        """
        return regex_of(production.rule, self.production) is not None

    # -- what a production opens and closes with ---------------------------

    def terminal_of(self, part: Rule) -> Terminal | None:
        """The one character a part matches, with the styles it carries.

        A part naming a macro is followed, so a marker keeps the class its own
        definition gave it — which is what tells `d` apart from the body it
        opens.
        """
        char = single_character(part)
        if char is not None:
            return (char, [])
        if isinstance(part, Reference):
            production = self.production(part.name)
            if production is not None and len(production.alternatives) == 1:
                char = single_character(production.alternatives[0])
                if char is not None:
                    return (char, styles_of(production))
        return None

    def spanning_alternatives(self, production: Production) -> list[list[Rule]]:
        """The alternatives long enough to open and close something.

        An alternative of one part brackets nothing — `d Atom = Number / \\( Expr \\)`
        has one of each — so it is left to the context that reached the
        production.
        """
        return [
            parts
            for alternative in production.alternatives
            if len(parts := parts_of(alternative)) >= 2
        ]

    def brackets_of(self, production: Production) -> tuple[Terminal, Terminal] | None:
        """The fixed pair a production wraps things in, or None.

        Every spanning alternative must agree on the pair, and neither end may
        be a newline: a pair is what an editor folds, and a line break is not
        text.
        """
        found: tuple[Terminal, Terminal] | None = None
        for parts in self.spanning_alternatives(production):
            opening, closing = self.terminal_of(parts[0]), self.terminal_of(parts[-1])
            if opening is None or closing is None:
                return None
            if "\n" in (opening[0], closing[0]):
                return None
            if found is not None and (found[0][0], found[1][0]) != (opening[0], closing[0]):
                return None
            found = (opening, closing)
        return found

    def line_openings_of(self, production: Production) -> list[Terminal]:
        """The characters a production opens with when it runs to a line break.

        This is a line role: `d …` is a definition to the end of its line, `# …`
        a comment to the end of its own. It closes where the line does rather
        than on a character, so it folds nothing and pops itself. Unlike a
        bracket pair the alternatives may disagree — an alternative line opens
        with `|` or with `/` — and each opening becomes a rule of its own
        entering the same context.

        A role reaching past its first line, as a definition reaches its
        alternative lines, is still one span: where it ends is what the chain of
        line contexts works out.
        """
        found: list[Terminal] = []
        alternatives = self.spanning_alternatives(production)
        if not alternatives or len(alternatives) != len(production.alternatives):
            return []
        if not self.crosses_line(production.rule):
            return []
        for parts in alternatives:
            opening = self.terminal_of(parts[0])
            if opening is None or opening[0] == "\n":
                return []
            if opening[0] not in [char for char, _ in found]:
                found.append(opening)
        return found

    # -- line breaks -------------------------------------------------------

    def crosses_line(self, node: Rule) -> bool:
        """Whether a node can reach a newline, transparent macros included.

        A grammar naming its line break — `d NL = \\n` — hides one behind a
        reference, and a node that can reach one is never one rule's worth of
        matching.
        """
        return self._crosses(node, seen=frozenset())

    def _crosses(self, node: Rule, seen: frozenset[str]) -> bool:
        for found in walk(node):
            if is_newline(found):
                return True
            if isinstance(found, Reference) and found.name not in seen:
                production = self.production(found.name)
                if production is not None and self.of(production) == INLINE:
                    if self._crosses(production.rule, seen | {found.name}):
                        return True
        return False


# -- building --------------------------------------------------------------


class MachineBuilder:
    """Derives the machine from a target: one context per place a line begins.

    The walk is demand-driven — a state is requested, built, and whatever it
    reaches is requested in turn — so a recursive grammar terminates for the
    same reason the resolver does.
    """

    def __init__(self, parse: Target, order: list[str] | None = None) -> None:
        self.parse = parse
        #: The order tokens are tried in, from `Lex`'s `File` where there is one.
        self.order = order or []
        self.classify = Classifier(parse)
        self.splitter = Splitter(self.classify)
        self.machine = Machine()
        self.names = NameAllocator()
        #: The context each state key was given.
        self.states: dict[str, str] = {}
        #: The context each span production's body is read in.
        self.spans: dict[str, str] = {}

    # -- the whole machine -------------------------------------------------

    def build(self) -> Machine:
        """Build every context, starting at the target's `File`."""
        start = self.classify.production(START_PRODUCTION)
        if start is None:
            return self.machine
        self.machine.start = self.context_for(
            [start.rule], name=START_PRODUCTION, styles=[], depth=0
        )
        return self.machine

    # -- contexts ----------------------------------------------------------

    def context_for(
        self,
        tails: list[Rule],
        name: str,
        styles: list[str],
        depth: int,
        escapable: bool = False,
        pushed: bool = False,
    ) -> str:
        """The context a set of rule tails begins a line in, built once per state.

        A state is *what may be matched here and what follows it*, not the rule
        trees it was reached through: `File` and the repetition it unfolds into
        leave the same thing behind and are one context. `depth` counts the
        contexts pushed to reach this one within the same production, which is
        what a chained line context pops back over, and `escapable` says whether
        leaving that way is allowed at all — a bracketed span ends on its
        closing character and nowhere else.

        `pushed` marks the body of a span. Such a state is entered by a push and
        left by a pop, which the state a document starts in is neither, so the
        two never share a context however alike what they match — a grammar whose
        brackets hold exactly what the file holds would otherwise pop at the top.
        """
        if depth > MAX_LINE_STATES:
            raise GeneratorError(
                f"the rule {_role_of(name)!r} leaves more behind after every line "
                "break, so it never reaches a line it could end on. A highlighter "
                "reads one line at a time, and a role that carries on has to carry "
                "on into the same thing each time"
            )

        parts, leftovers = self.reading(tails)
        # The styles and the way in belong to the key: an attribute line and an
        # alternative line may leave the same thing behind and still not be the
        # same state.
        key = f"{self.signature(tails)}#{depth}#{','.join(styles)}#{pushed:d}"
        found = self.states.get(key)
        if found is not None:
            return found

        context = Context(
            name=self.names.allocate(safe_identifier(name) or "Context"),
            styles=list(styles),
            origin=name,
        )
        self.states[key] = context.name
        self.machine.contexts[context.name] = context
        # Extended rather than assigned: the walk below reaches the states this
        # one leads to, and a span whose body is this very state inserts its
        # closing rule while we are still here. Assigning would drop it.
        context.rules.extend(self.rules_for(parts, styles))

        if escapable and depth > 0:
            # A chain must be able to leave: a line beginning with something
            # none of its rules knows pops the whole chain, so the context below
            # reads that line from its first character.
            context.rules.append(
                ContextRule(match=Match(rule=_any_character(), look_ahead=True), pop=depth + 1)
            )

        # Where the next line begins: the leftovers, as a state of their own. A
        # state whose next line is itself simply stays, which is what a run of
        # lines all alike — a scope, the lines of a group — amounts to. A
        # leftover of nothing is a line role that has said all it had to say.
        following = [left for left in leftovers if key_of(left) != key_of(EMPTY)]
        if not following:
            if leftovers and escapable:
                context.line_end = POP
        elif self.signature(following) == self.signature(tails):
            context.line_end = STAY
        else:
            context.line_end = self.context_for(
                following, f"{name}Line", styles, depth + 1, escapable, pushed
            )
        return context.name

    # -- states ------------------------------------------------------------

    def reading(self, tails: list[Rule]) -> tuple[list[Rule], list[Rule]]:
        """What a state matches on its line, and what it leaves for the next."""
        parts: list[Rule] = []
        leftovers: list[Rule] = []
        for tail in tails:
            line = self.splitter.read(tail)
            _extend(parts, line.parts)
            _extend(leftovers, line.leftovers)
        return parts, leftovers

    def signature(self, tails: list[Rule]) -> str:
        """What tells one state from another, whatever it was reached through."""
        parts, leftovers = self.reading(tails)
        return f"{_state_key(parts)}=>{_state_key(leftovers)}"

    # -- rules -------------------------------------------------------------

    def rules_for(self, parts: list[Rule], styles: list[str]) -> list[ContextRule]:
        """The rules a line's worth of parts contributes, pushes before matches.

        A push comes first so an opening character is not eaten by a token of
        the same shape; among the matches the `Lex` order wins where the grammar
        gave one, and the order written wins otherwise.
        """
        pushes: list[ContextRule] = []
        matches: list[tuple[int, ContextRule]] = []
        seen: set[str] = set()

        for part in self.expanded(parts):
            key = key_of(part)
            if key in seen:
                continue
            seen.add(key)
            part = self.tightened(part)
            if part is None:
                continue
            production = self._referenced(part)
            if production is None:
                matches.append((len(self.order), ContextRule(match=Match(part), styles=list(styles))))
                continue
            kind = self.classify.of(production)
            if kind == SPAN:
                pushes.extend(self.span_rules(production, styles))
            elif kind == TOKEN:
                rank = self.order.index(production.name) if production.name in self.order else len(self.order)
                matches.append(
                    (rank, ContextRule(match=Match(part), styles=styles_of(production)))
                )
            else:  # transparent, and one expression's worth of matching
                matches.append(
                    (len(self.order), ContextRule(match=Match(part), styles=list(styles)))
                )

        matches.sort(key=lambda ranked: ranked[0])
        return _distinct(pushes + [rule for _, rule in matches], self.classify.production)

    def expanded(self, parts: list[Rule]) -> list[Rule]:
        r"""The parts with every transparent call replaced by what it holds.

        A part reached through the splitter is already atomic, but one taken
        straight from an alternative — `d Atom = Number / Skipped / \( Expr \)`
        — may still name a macro standing for several rules, and each of them
        wants its own class.
        """
        out: list[Rule] = []
        for part in parts:
            production = self._referenced(part)
            if (
                production is not None
                and self.classify.of(production) == INLINE
                and not self.splitter.atomic(part)
            ):
                out.extend(self.expanded(self.splitter.read(production.rule).parts))
            else:
                out.append(part)
        return out

    def tightened(self, part: Rule) -> Rule | None:
        """A part that must match something, or None when it cannot be made to.

        A rule matching nothing makes no progress, and a highlighter trying it at
        every position would never move on. But a part is often nullable only
        because it is optional where it stands — `( WS )?` between two items —
        and the run of whitespace it wraps is exactly the rule the context
        wants, so the optionality is dropped rather than the rule.
        """
        if not nullable(part, self.classify.production):
            return part
        if isinstance(part, Repetition) and part.minimum == 0:
            body = self.tightened(part.body)
            if body is not None:
                return Repetition(body, 1, part.maximum, "+" if part.marker == "*" else "")
        if isinstance(part, Choice):
            options = [
                tight
                for option in part.options
                if (tight := self.tightened(option)) is not None
            ]
            if options:
                return options[0] if len(options) == 1 else Choice(options, part.symbol)
        return None

    def span_rules(self, production: Production, styles: list[str]) -> list[ContextRule]:
        """The rules entering a span, and the rules its short alternatives give.

        `d Atom = Number / \\( Expr \\)` brackets with one alternative and matches
        a token with the other, so the context that reached it needs both. A
        line span may be entered by several characters — `|` and `/` both open
        an alternative line — and each becomes a rule of its own.
        """
        rules: list[ContextRule] = []
        brackets = self.classify.brackets_of(production)
        inner = self.span_context(production)

        if brackets is not None:
            (opening, opening_styles), _ = brackets
            rules.append(
                ContextRule(
                    match=Match(
                        _character(opening), word_boundary=_is_word_character(opening)
                    ),
                    styles=opening_styles or styles_of(production),
                    push=inner,
                    region=production.name,
                )
            )
        else:
            for opening, opening_styles in self.classify.line_openings_of(production):
                rules.append(
                    ContextRule(
                        match=Match(
                            _character(opening),
                            word_boundary=_is_word_character(opening),
                        ),
                        styles=opening_styles or styles_of(production),
                        push=inner,
                    )
                )

        # Whatever the production also matches without bracketing anything.
        short = [
            parts[0]
            for alternative in production.alternatives
            if len(parts := parts_of(alternative)) == 1
        ]
        rules.extend(self.rules_for(short, styles))
        return rules

    def span_context(self, production: Production) -> str:
        """The context a span's body is read in, built once per production."""
        found = self.spans.get(production.name)
        if found is not None:
            return found
        brackets = self.classify.brackets_of(production)
        styles = styles_of(production)
        bodies: list[Rule] = []
        for parts in self.classify.spanning_alternatives(production):
            # Everything between the opening and, for a bracketing span, the
            # closing character; a line span keeps everything after its opening.
            bodies.append(_sequence(list(parts[1:-1] if brackets else parts[1:])))
        name = self.context_for(
            bodies,
            production.name,
            styles,
            depth=0,
            escapable=brackets is None,
            pushed=True,
        )

        context = self.machine.contexts[name]
        if brackets is not None:
            _, (closing, closing_styles) = brackets
            closer = ContextRule(
                match=Match(_character(closing)),
                styles=closing_styles or styles,
                pop=1,
                region=production.name,
            )
            # The closing character comes first, so nothing else may eat it. Two
            # places reaching the same span share its context, and it needs the
            # rule only once.
            if not any(_same_rule(rule, closer) for rule in context.rules):
                context.rules.insert(0, closer)
        self.spans[production.name] = name
        if brackets is None and context.line_end == STAY:
            # A line role of a single line ends where its line does. One that
            # carries on — a definition and its alternative lines — leaves
            # through the chain instead, and keeps the context that chain names.
            context.line_end = POP
        return name

    # -- reading a part ----------------------------------------------------

    def _referenced(self, part: Rule) -> Production | None:
        """The production a part calls, when it is nothing but a call."""
        if isinstance(part, Reference):
            return self.classify.production(part.name)
        return None


def _same_rule(one: ContextRule, other: ContextRule) -> bool:
    """Whether two rules match the same text and do the same thing with it."""
    return (
        key_of(one.match.rule) == key_of(other.match.rule)
        and one.match.look_ahead == other.match.look_ahead
        and one.match.word_boundary == other.match.word_boundary
        and one.push == other.push
        and one.pop == other.pop
        and one.styles == other.styles
    )


def _distinct(rules: list[ContextRule], lookup) -> list[ContextRule]:
    """Drop the rules a context already has.

    Several parts of a grammar reach the same terminal — every alternative of a
    group closes with the same bracket — and a context gains nothing from being
    told twice. Two rules are the same when they match the same text and do the
    same thing with it.
    """
    seen: set[tuple] = set()
    out: list[ContextRule] = []
    for rule in rules:
        pattern = regex_of(rule.match.rule, lookup) or key_of(rule.match.rule)
        key = (
            pattern,
            rule.match.look_ahead,
            rule.match.word_boundary,
            rule.push,
            rule.pop,
            tuple(rule.styles),
        )
        if key not in seen:
            seen.add(key)
            out.append(rule)
    return out


def _role_of(name: str) -> str:
    """The production a chain of line contexts was named after.

    Each further line of a role is named `…Line`, so the production is what is
    left once those are taken off.
    """
    while name.endswith("Line"):
        name = name[: -len("Line")]
    return name or "File"


def _state_key(tails: list[Rule]) -> str:
    """What identifies a state: the leftovers it holds, however they were found."""
    return "|".join(sorted(key_of(tail) for tail in tails))


#: Where a rule the machine invented came from. It is not in any file, and
#: nothing reports it, but every node carries a span and this is a valid one.
_NOWHERE = Span(Position(0, 1, 1), Position(0, 1, 1))


def _item(text: str) -> Item:
    """An item spelling the given text, for a rule the machine builds itself."""
    return Item(span=_NOWHERE, parts=[Text(span=_NOWHERE, value=text)])


def _character(char: str) -> Rule:
    """A rule matching one fixed character."""
    return MacroCall(macro=CHARACTER, item=_item(char))


def _is_word_character(char: str) -> bool:
    """Whether a character is one a word may be made of."""
    return char.isalnum() or char == "_"


def _any_character() -> Rule:
    """A rule matching any one character, for a look-ahead that only pops.

    MGFF has no negated set, so "anything" is spelled as the union of the
    categories — which is every character a line may hold.
    """
    return MacroCall(macro=CHARACTER_SET, item=_item(_ANYTHING))


#: Every character that can begin something, as a character set spells it.
#: Whitespace is left out on purpose: a chained line context is left by what its
#: line *starts* with, and an indent starts nothing.
_ANYTHING = "Letter|Mark|Number|Punctuation|Symbol"
