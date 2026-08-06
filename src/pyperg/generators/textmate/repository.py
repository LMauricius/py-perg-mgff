"""Building a TextMate grammar's repository from the `Lex` and `Parse` targets.

TextMate highlights with a stack of **patterns**. A `match` pattern consumes
what it matched; a `begin`/`end` pattern pushes, matches its own `patterns`
until the `end` expression fires, and pops. That is the same pushdown machine
Kate's contexts are, so both backends read a grammar through `utils.machine` and
differ only in how they spell the answer.

    Machine                Kate                   TextMate
    --------------------------------------------------------------------
    Context                <context>              a repository entry
    Context.styles         attribute=             contentName
    ContextRule.push       context="X"            begin, with nested patterns
    ContextRule.pop        context="#pop"         the end expression
    Context.line_end #pop  lineEndContext="#pop"  end: "$"
    Context.line_end <C>   lineEndContext="C"     while: what C's lines open with

**A context holds what its place in the grammar reaches, and nothing else.** A
definition's `d` is a keyword because a line may open with one there; a subgroup
holds no `d` rule because nothing spelling a definition is reachable inside one;
a comment keeps its `contentName` across the lines its group spans.

**`while` is how a line role carries on.** A definition covers its alternative
and attribute lines, which no `end` expression can recognise without lookahead —
but `while` is exactly "this span continues as long as the next line starts like
this", which is what the chained line contexts of the machine say.

**`Lex` keeps two jobs**: the expression each token matches with, and the order
tokens are tried in where a context holds several. A grammar with no `Parse`
target is a machine of one context, and is built straight from that order.

```mermaid
stateDiagram-v2
    [*] --> file
    file --> definition: <code>d</code> begins
    definition --> definition: <code>|</code> while
    definition --> [*]: any other line ends
    file --> comment: <code>#</code> begins
    comment --> comment_group: <code>(</code> begins
    comment --> [*]: end of line
```
"""

from __future__ import annotations

import sys

from ...diagnostics.errors import GeneratorError
from ...mgff.common.rules import Reference, Rule
from ...mgff.semantics.model import GrammarModel, Production, Target
from ..utils.styles import styles_of
from ..utils.highlight import token_order
from ..utils.machine import POP, STAY
from ..utils.machine import Context as MachineContext
from ..utils.machine import ContextRule as MachineRule
from ..utils.machine import MachineBuilder
from ..utils.naming import NameAllocator, safe_identifier, snake_case
from ..utils.regex import regex_of
from ..utils.walk import single_character
from .patterns import Pattern, include, match_pattern, matches_nothing, regex_for
from .scopes import punctuation_scope, region_scope, scope_for

#: The repository entries this backend always builds.
GRAMMAR_ENTRY = "grammar"
TOKENS_ENTRY = "tokens"

#: The targets the backend understands.
LEX_TARGET = "Lex"
PARSE_TARGET = "Parse"

#: How a line role says it is over: the first line that does not carry it on.
#: Zero-width and anchored at the line's start, so the line is then read by
#: whatever the role was written inside, exactly as it would have been.
#: An indent comes before the marker, since layout is arbitrary in MGFF.
CARRIES_ON = r"^(?!\s*(?:{})|\s*$)"


class RepositoryBuilder:
    """Turns a resolved grammar into a TextMate repository and its top patterns.

    `language` is the identifier every scope name ends in, which the generator
    settles before the repository is built.
    """

    def __init__(self, model: GrammarModel, language: str) -> None:
        self.model = model
        self.language = language
        self.lex = model.target(LEX_TARGET)
        self.parse = model.target(PARSE_TARGET)
        #: The repository, in the order the entries were built.
        self.entries: dict[str, Pattern] = {}
        #: What a document is matched against before anything has been pushed.
        self.top: list[Pattern] = []
        self.names = NameAllocator({GRAMMAR_ENTRY, TOKENS_ENTRY})
        #: The pairs an editor folds and auto-closes, from the spans that nest.
        self.pairs: list[tuple[str, str]] = []
        #: Every context of the machine, and the entry each push was given.
        self.contexts: dict[str, MachineContext] = {}
        self.pushed: dict[str, str] = {}
        if self.lex is None and self.parse is None:
            raise GeneratorError(
                "the grammar has no `Lex` or `Parse` target; the TextMate backend "
                "generates from those two"
            )
        self._warn_about_other_targets()

    def _warn_about_other_targets(self) -> None:
        """Say which targets are being ignored, rather than dropping them silently."""
        for target in self.model.targets:
            if target.name not in (LEX_TARGET, PARSE_TARGET):
                print(
                    f"pyperg: textmate: target {target.name!r} is not generated; "
                    f"this backend reads {LEX_TARGET} and {PARSE_TARGET}.",
                    file=sys.stderr,
                )

    # -- the whole grammar -------------------------------------------------

    def build(self) -> None:
        """Build every repository entry, and the patterns a document starts in.

        A grammar with a `Parse` target is spelled from the machine; one with
        only tokens is the flat list `Lex` names, in that order.
        """
        if self.parse is not None:
            self.build_machine()
        else:
            assert self.lex is not None
            self.build_tokens(self.lex)
            self.top = [include(TOKENS_ENTRY)]

    def top_patterns(self) -> list[Pattern]:
        """What a document is matched against before anything has been pushed."""
        return self.top

    def repository(self) -> dict[str, Pattern]:
        """Every entry, in the order they were built."""
        return self.entries

    def bracket_pairs(self) -> list[tuple[str, str]]:
        """The character pairs an editor should fold and auto-close."""
        return self.pairs

    # -- the machine -------------------------------------------------------

    def build_machine(self) -> None:
        """Spell the machine: the starting context on top, a span per push."""
        assert self.parse is not None
        order = token_order(self.lex) if self.lex is not None else []
        machine = MachineBuilder(self.parse, order).build()
        self.contexts = machine.contexts

        start = machine.contexts.get(machine.start)
        if start is None:
            raise GeneratorError(
                f"target {PARSE_TARGET!r} describes no structure to highlight"
            )
        # `grammar` is filled in place, so it is written out ahead of the spans
        # it names, and a span reaching back to it finds it already there.
        patterns: list[Pattern] = []
        self.entries[GRAMMAR_ENTRY] = {"patterns": patterns}
        self.top = [include(GRAMMAR_ENTRY)]
        patterns.extend(self.patterns_of(start))

    def patterns_of(self, context: MachineContext) -> list[Pattern]:
        """A context's rules as patterns: a span to include, or a match.

        A rule that only pops is left out — it is the `end` of the entry this
        context belongs to — and so is a look-ahead, which is Kate's way of
        leaving a chain and `while`'s job here.
        """
        patterns: list[Pattern] = []
        for rule in context.rules:
            if rule.match.look_ahead or (rule.pop and not rule.push):
                continue
            if rule.push:
                entry = self.span_entry(rule)
                if entry is not None:
                    patterns.append(include(entry))
            else:
                pattern = self.match_of(rule)
                if pattern is not None:
                    patterns.append(pattern)
        return patterns

    def span_entry(self, rule: MachineRule) -> str | None:
        """The entry a push rule opens, built once per opening.

        A context entered by several characters — an alternative line opens with
        `|` or with `/` — becomes one entry per opening, since the opening is
        part of the entry here rather than a rule pointing at it.
        """
        context = self.contexts.get(rule.push or "")
        if context is None:
            return None
        opening = regex_for_rule(rule, self.lookup)
        if opening is None:
            return None
        key = f"{rule.push}:{opening}"
        if key in self.pushed:
            return self.pushed[key]

        name = self.names.allocate(
            snake_case(safe_identifier(context.origin or context.name)) or "span"
        )
        self.pushed[key] = name
        entry: Pattern = {}
        self.entries[name] = entry
        entry.update(self.span_pattern(context, rule, opening))
        return name

    def span_pattern(
        self, context: MachineContext, rule: MachineRule, opening: str
    ) -> Pattern:
        """One span: where it begins, where it ends, and what it holds.

        Three ways to end, in the order the machine offers them: a closing
        character, which is also the pair an editor folds; the end of the line;
        or the first line that does not carry the role on, which is `while`.
        """
        scope = scope_for(rule.styles, self.language)
        pattern: Pattern = {
            "name": region_scope(context.origin or context.name, self.language),
            "begin": opening,
            "beginCaptures": {
                "0": {
                    "name": scope
                    or punctuation_scope(context.origin, self.language, "begin")
                }
            },
        }
        content = scope_for(context.styles, self.language)
        if content is not None:
            pattern["contentName"] = content

        closing = self.closing_rule(context)
        if closing is not None:
            closing_regex = regex_for_rule(closing, self.lookup) or "$"
            pattern["end"] = closing_regex
            closing_scope = scope_for(closing.styles, self.language)
            pattern["endCaptures"] = {
                "0": {
                    "name": closing_scope
                    or punctuation_scope(context.origin, self.language, "end")
                }
            }
            self.record_pair(opening, closing)
        elif context.line_end == POP or context.line_end == STAY:
            # A role of a single line ends where its line does.
            pattern["end"] = "$"
        else:
            pattern["end"] = self.carry_expression(context)

        pattern["patterns"] = self.patterns_of(context) + self.chained_patterns(context)
        return pattern

    def closing_rule(self, context: MachineContext) -> MachineRule | None:
        """The rule that leaves a context on a character of its own."""
        for rule in context.rules:
            if rule.pop and not rule.push and not rule.match.look_ahead:
                return rule
        return None

    def record_pair(self, opening: str, closing: MachineRule) -> None:
        """Remember a fixed pair, which the editor folds and auto-closes."""
        open_char = opening[-1] if len(opening) <= 2 else ""
        close_char = single_character(closing.match.rule) or ""
        pair = (open_char, close_char)
        if open_char and close_char and pair not in self.pairs:
            self.pairs.append(pair)

    # -- chains ------------------------------------------------------------

    def chain_of(self, context: MachineContext) -> list[MachineContext]:
        """The line contexts a role carries on into, in order.

        A definition's alternative lines and attribute lines are states of their
        own in the machine. TextMate has no way to move between them at the end
        of a line, so the span holds all of their rules and lets `while` say how
        long it lasts — a fair reading, since what the lines may hold is what
        the grammar allows, only not in which order.
        """
        found: list[MachineContext] = []
        name = context.line_end
        while name not in (STAY, POP) and name not in [c.name for c in found]:
            following = self.contexts.get(name)
            if following is None or following is context:
                break
            found.append(following)
            name = following.line_end
        return found

    def chained_patterns(self, context: MachineContext) -> list[Pattern]:
        """What the lines a role carries on into may hold."""
        patterns: list[Pattern] = []
        for following in self.chain_of(context):
            patterns.extend(self.patterns_of(following))
        return patterns

    def carry_expression(self, context: MachineContext) -> str:
        """Where a role that reaches past its first line stops.

        Built from the rules of the chained contexts: their openings are exactly
        the markers a continuation line may begin with, so the role ends at the
        first line beginning with none of them.

        This is an `end` rather than a `while` on purpose. A `while` is tested at
        the start of every line whatever is open at the time, and would cut a
        group that spans lines in half; an `end` waits until the spans inside
        have closed, which is the behaviour the machine describes.
        """
        openings: list[str] = []
        for following in self.chain_of(context):
            for rule in following.rules:
                if rule.match.look_ahead:
                    continue
                found = regex_for_rule(rule, self.lookup)
                if found is not None and found not in openings:
                    openings.append(found)
        if not openings:
            return "^"  # nothing carries it on, so the next line ends it
        return CARRIES_ON.format("|".join(openings))

    # -- Lex ---------------------------------------------------------------

    def build_tokens(self, lex: Target) -> None:
        """One entry per token `File` names, and one including them in order.

        This is what a grammar with no `Parse` target amounts to: a machine of
        one context, whose rules are the tokens, tried in the order written.
        """
        includes: list[Pattern] = []
        self.entries[TOKENS_ENTRY] = {"patterns": includes}
        for name in token_order(lex):
            entry = self.entry_for_token(lex.productions[name])
            if entry is not None:
                includes.append(include(entry))

    def entry_for_token(self, production: Production) -> str | None:
        """One token production as its own `match` entry; returns the entry name.

        A production whose expression could match nothing is skipped with a note
        on standard error: a zero-width pattern never highlights anything, and
        leaving it in would only slow the tokeniser down.
        """
        if matches_nothing(production, self.lex_lookup):
            print(
                f"pyperg: textmate: token {production.name!r} can match the empty "
                "string, so it is left out; a zero-width pattern highlights nothing.",
                file=sys.stderr,
            )
            return None
        name = self.entry_name(production)
        scope = scope_for(styles_of(production), self.language)
        self.entries[name] = match_pattern(production, scope, self.lex_lookup)
        return name

    def lex_lookup(self, name: str) -> Production | None:
        """A `Lex` production by name, for the expressions that inline it."""
        return self.lex.productions.get(name) if self.lex is not None else None

    # -- matching ----------------------------------------------------------

    def lookup(self, name: str) -> Production | None:
        """A production of either target, for the expressions that inline it."""
        found = self.parse.productions.get(name) if self.parse is not None else None
        return found if found is not None else self.lex_lookup(name)

    def match_of(self, rule: MachineRule) -> Pattern | None:
        """One machine rule as a pattern: an entry to include, or a match.

        A rule that is nothing but a call becomes **an entry of its own**, named
        after the macro and included wherever the macro is reachable. That costs
        nothing at run time and is what makes the output worth reading — and
        worth hand-tuning — instead of repeating one expression in every context
        that can reach it. It is also spelled from the whole production, so a
        choice of fixed words keeps its boundaries and the `Lu` of `Lucky` is
        not a category.
        """
        called = self.called_production(rule)
        if called is not None:
            name = self.token_entry(called, rule)
            if name is not None:
                return include(name)
            return None
        expression = regex_for_rule(rule, self.lookup)
        if expression is None:
            return None
        return _match(expression, scope_for(rule.styles, self.language))

    def called_production(self, rule: MachineRule) -> Production | None:
        """The production a plain match rule calls, when that is all it does."""
        if rule.push or rule.pop or rule.match.look_ahead:
            return None
        if isinstance(rule.match.rule, Reference):
            return self.lookup(rule.match.rule.name)
        return None

    def token_entry(self, production: Production, rule: MachineRule) -> str | None:
        """The entry one token is filed under, built once and included after.

        Keyed by the styles as well as the macro: the same name is a name
        wherever it is written, but on an attribute line it is an attribute, and
        the two want scopes of their own.
        """
        expression = regex_for_rule(rule, self.lookup)
        if expression is None:
            return None
        # Keyed by the scope rather than the styles: `Normal` and no style at
        # all both mean "no scope", and one entry serves both.
        scope = scope_for(rule.styles, self.language)
        name = self.entry_name(production, scope)
        if name not in self.entries:
            self.entries[name] = _match(expression, scope)
        return name

    # -- naming ------------------------------------------------------------

    def entry_name(self, production: Production, scope: str | None = None) -> str:
        """The repository key a production is filed under.

        Repository keys are conventionally lower case, and two targets may name
        a production the same, so the allocator is keyed by the production's
        origin as well as its name — and by the scope it was reached with, since
        the same name is a name in a body and an attribute on an attribute line.
        """
        wanted = snake_case(safe_identifier(production.name)) or "rule"
        return self.names.allocate(
            wanted, key=f"{production.origin}:{production.name}:{scope or ''}"
        )


def _match(expression: str, scope: str | None) -> Pattern:
    """A `match` pattern, scoped when its styles name a scope at all."""
    pattern: Pattern = {}
    if scope is not None:
        pattern["name"] = scope
    pattern["match"] = expression
    return pattern


def regex_for_rule(rule: MachineRule, lookup) -> str | None:
    """The expression a machine rule matches with.

    A plain call is spelled from the production it names, which is what keeps
    the word boundaries a keyword list is worth; anything else is spelled from
    the rule tree it was built with.
    """
    node: Rule = rule.match.rule
    found: str | None
    if isinstance(node, Reference):
        production = lookup(node.name)
        if production is None:
            return None
        try:
            found = regex_for(production, lookup)
        except GeneratorError:
            return None
    else:
        found = regex_of(node, lookup)
    if found is not None and rule.match.word_boundary:
        # A marker spelled as a letter must not open a line inside a word.
        found = rf"\b{found}\b"
    return found
