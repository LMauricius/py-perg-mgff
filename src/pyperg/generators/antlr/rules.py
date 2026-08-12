"""Rule trees as the text of an ANTLR rule.

Two things about ANTLR shape everything here.

**A parser rule cannot match a character.** It reads tokens, so a character set
belongs to a lexer rule and nowhere else. A single character is the exception,
because ANTLR reads a literal in a parser rule as an implicit token of its own —
which is what lets a grammar write `'(' expr ')'` and never name the brackets.

**A literal is a string, not a character.** MGFF has none longer than one
character, so `< =` arrives as two nodes and has to be fused back into `'<='`
before it is written; `utils.walk.merge_adjacent_literals` is what does it, and
without it every operator would go out as a run of one-character literals.

Where a match goes is spelled at the call site rather than at the rule, which is
the one place ANTLR reads a grammar the other way round from MGFF. `store(f)`
becomes `f=`, `push(l)` becomes `l+=`, and since the label belongs to the rule in
MGFF, every reference to that rule carries it.
"""

from __future__ import annotations

from ...diagnostics.errors import GeneratorError
from ...mgff.common.characters import character_set_matched_by
from ...mgff.common.rules import Choice, MacroCall, Reference, Repetition, Rule, Sequence
from ...mgff.systems.model import Production
from ..utils.naming import NameAllocator, safe_identifier, snake_case
from ..utils.walk import literal_of, merge_adjacent_literals, top_level_parts
from .charset import antlr_character_set, antlr_literal
from .phases import AntlrPhases

#: Words ANTLR keeps for itself, in either case a rule name may take.
ANTLR_RESERVED = frozenset(
    {
        "grammar", "lexer", "parser", "options", "tokens", "channels", "import",
        "fragment", "mode", "returns", "locals", "throws", "catch", "finally",
        "rule", "EOF",
    }
)

#: The markers ANTLR writes a repetition with. It has no counted form, so a
#: repetition bounded any other way has nothing to become.
_REPETITION_MARKERS = {(0, 1): "?", (0, None): "*", (1, None): "+"}


def _fixed_length(node: Rule) -> int:
    """How many characters a rule matches when that number is fixed, else -1."""
    literal = literal_of(node)
    return len(literal) if literal is not None else -1


def preference_order(options: list[Rule], symbol: str) -> list[Rule]:
    """A choice's options in the order they should be tried.

    `/` takes the first that succeeds, which is exactly what ANTLR's alternation
    does, so the written order stands. `|` takes the longest, which the parser
    cannot express, so the longest fixed option goes first — enough to make `<=`
    win over `<`, which is the case the marker exists for. The lexer needs no
    help: it matches the longest alternative of a rule whatever their order.
    """
    if symbol != "|":
        return list(options)
    return sorted(options, key=_fixed_length, reverse=True)


class RuleNames:
    """A name in the grammar for every production, in ANTLR's two cases.

    ANTLR tells a parser rule from a lexer rule by its first letter, so the two
    namespaces cannot collide however a grammar names its macros.
    """

    def __init__(self, phases: AntlrPhases) -> None:
        parser_names = NameAllocator({word.lower() for word in ANTLR_RESERVED})
        lexer_names = NameAllocator({word.upper() for word in ANTLR_RESERVED})
        self.by_production: dict[str, str] = {}
        for name in phases.parser_rules:
            self.by_production[name] = parser_names.allocate(
                snake_case(safe_identifier(name, fallback="rule")) or "rule", key=name
            )
        for name in phases.lexer_rules:
            self.by_production[name] = lexer_names.allocate(
                snake_case(safe_identifier(name, fallback="token")).upper() or "TOKEN",
                key=name,
            )

    def of(self, name: str) -> str:
        """The name a production is written under, or the name itself if unknown."""
        return self.by_production.get(name, name)


class RuleWriter:
    """Writes one production's alternatives as ANTLR reads them."""

    def __init__(self, phases: AntlrPhases, names: RuleNames) -> None:
        self.phases = phases
        self.names = names
        #: The fields of the rule being written that a loop matches more than
        #: once. ANTLR refuses `f=rule` there and wants `f+=rule`, and it wants
        #: one or the other throughout a rule, so the whole body is read for
        #: them before any of it is written.
        self.list_fields: set[str] = set()

    # -- a whole production ------------------------------------------------

    def alternatives(self, production: Production, in_lexer: bool) -> list[str]:
        """Every alternative of a production, in the order it should be tried."""
        options = preference_order(production.alternatives, production.choice_symbol or "/")
        self.list_fields = set() if in_lexer else self._fields_a_loop_repeats(production)
        written = [self.alternative(option, in_lexer) for option in options]
        if in_lexer and any(not text for text in written):
            raise GeneratorError(
                f"an alternative of the lexer rule {production.name!r} matches "
                "nothing at all, and a token has to consume a character"
            )
        return written

    # -- one alternative ---------------------------------------------------

    def alternative(self, node: Rule, in_lexer: bool) -> str:
        """A run of elements, with the runs that spell a string fused into one."""
        parts = merge_adjacent_literals(top_level_parts(node))
        return " ".join(self.element(part, in_lexer) for part in parts)

    def element(self, node: Rule, in_lexer: bool) -> str:
        """One element of an alternative, bracketed where it has to be."""
        literal = literal_of(node)
        if literal is not None:
            return antlr_literal(literal)

        if isinstance(node, MacroCall):
            return self._macro_call(node, in_lexer)
        if isinstance(node, Reference):
            return self._reference(node, in_lexer)
        if isinstance(node, Repetition):
            return self.element(node.body, in_lexer) + self._marker(node)
        if isinstance(node, Choice):
            options = preference_order(node.options, node.symbol)
            return "( " + " | ".join(self.alternative(one, in_lexer) for one in options) + " )"
        # A sequence reaching here is a repetition's body or a choice's option;
        # `top_level_parts` has already flattened away every other one.
        text = self.alternative(node, in_lexer)
        if not text:
            raise GeneratorError(
                "an element of this rule matches nothing at all, and ANTLR has "
                "no empty group to write it as"
            )
        return f"( {text} )"

    # -- the pieces --------------------------------------------------------

    def _macro_call(self, node: MacroCall, in_lexer: bool) -> str:
        """A character set, which only a lexer rule may hold.

        A set of one character never reaches here: `literal_of` has already
        written it as the literal a parser rule accepts too.
        """
        characters = character_set_matched_by(node)
        if characters is None:
            raise GeneratorError(
                f"the item {node.item.text!r} is a construct this backend does "
                "not know how to write"
            )
        if not in_lexer:
            raise GeneratorError(
                f"the parser reads tokens, so the set {node.item.text!r} matches "
                "nothing there; give it a rule of its own in the lexer phase and "
                "call that instead"
            )
        return antlr_character_set(characters)

    def _reference(self, node: Reference, in_lexer: bool) -> str:
        """A call on another rule, carrying the label the called rule asks for."""
        if not in_lexer and self.phases.is_fragment(node.name):
            raise GeneratorError(
                f"the parser calls {node.name!r}, which is a fragment and produces "
                "no token. Write `> token` on it, or push it to the list the "
                "parser reads."
            )
        written = self.names.of(node.name)
        if in_lexer:
            # ANTLR lexer rules take no labels: a token has no fields.
            return written
        label = self.phases.label_of(node.name)
        if label is None:
            return written
        field, operator = label
        return f"{field}{'+=' if field in self.list_fields else operator}{written}"

    def _fields_a_loop_repeats(self, production: Production) -> set[str]:
        """The fields of a rule that a repetition matches more than once.

        `?` is not one: it matches at most once, so what it holds is still a
        single field.
        """
        found: set[str] = set()

        def visit(node: Rule, in_loop: bool) -> None:
            if isinstance(node, Reference):
                label = self.phases.label_of(node.name)
                if label is not None and in_loop:
                    found.add(label[0])
            elif isinstance(node, Repetition):
                visit(node.body, in_loop or node.maximum != 1)
            elif isinstance(node, Choice):
                for option in node.options:
                    visit(option, in_loop)
            elif isinstance(node, Sequence):
                for item in node.items:
                    visit(item, in_loop)

        for alternative in production.alternatives:
            visit(alternative, in_loop=False)
        return found

    def _marker(self, node: Repetition) -> str:
        """The suffix repeating an element, for the three bounds ANTLR has."""
        marker = _REPETITION_MARKERS.get((node.minimum, node.maximum))
        if marker is None:
            raise GeneratorError(
                f"ANTLR repeats an element none, once or many times, and cannot "
                f"repeat one between {node.minimum} and {node.maximum} times"
            )
        return marker
