"""Building a TextMate grammar's repository from the `Lex` and `Parse` targets.

TextMate highlights with a stack of **patterns**. A `match` pattern consumes
what it matched; a `begin`/`end` pattern pushes, matches its own `patterns`
until the `end` expression fires, and pops. That is a pushdown machine over
text, exactly like Kate's contexts, so the two backends read a grammar the same
way — through `utils.highlight` — and differ only in how they spell the answer.

    Kate                          TextMate
    ------------------------------------------------------------
    context                       a repository entry
    a rule pushing a context      begin / end, with nested patterns
    `#pop`                        the `end` expression
    IncludeRules                  {"include": "#name"}
    itemData + default style      a scope name
    <list> of keywords            \\b(?:a|b|c)\\b

Both targets start at a macro named `File`.

**`Lex` maps exactly.** Every token production `File` names becomes a repository
entry of its own — one `match` pattern — and `tokens` includes them in the order
`File` wrote them. Giving each production its own entry is what makes the output
worth reading and editing by hand.

**`Parse` maps approximately**, in the same way and for the same reason as it
does for Kate: what a pushdown machine can genuinely reproduce from a grammar is
its *nesting*, so a production that brackets something becomes a `begin`/`end`
entry, and everything else contributes nothing.

One thing Kate must do that this backend does not: emit the loose terminals a
`Parse` grammar mentions. Kate colours every character of a document, so an
unmatched one is a gap; TextMate leaves unmatched text at the editor's default
colour, which is what those terminals would have been given anyway.

```mermaid
stateDiagram-v2
    [*] --> patterns
    patterns --> grammar: include
    grammar --> tokens: include
    grammar --> atom: ( begins
    atom --> grammar: include
    atom --> [*]: ) ends
```
"""

from __future__ import annotations

import sys

from ...diagnostics.errors import GeneratorError
from ...mgff.semantics.model import GrammarModel, Production, Target
from ..utils.classes import classes_of
from ..utils.highlight import brackets_of, reachable_productions, token_order
from ..utils.naming import NameAllocator, safe_identifier, snake_case
from ..utils.regex import escape_character
from .patterns import Pattern, include, match_pattern, matches_nothing
from .scopes import punctuation_scope, region_scope, scope_for

#: The repository entries this backend always builds.
GRAMMAR_ENTRY = "grammar"
TOKENS_ENTRY = "tokens"

#: The targets the backend understands.
LEX_TARGET = "Lex"
PARSE_TARGET = "Parse"


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
        self._bracketing: list[tuple[Production, tuple[str, str]]] | None = None
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

        A grammar with a `Parse` target starts at `grammar`, which reaches
        everything; one with only tokens starts at `tokens`. The entries are
        built in the order they should be read, since a repository is written
        out as it was filled in.
        """
        if self.parse is not None:
            self.build_grammar()
            self.build_bracket_entries()
        if self.lex is not None:
            self.build_tokens(self.lex)
        start = GRAMMAR_ENTRY if self.parse is not None else TOKENS_ENTRY
        self.top = [include(start)]

    def top_patterns(self) -> list[Pattern]:
        """What a document is matched against before anything has been pushed."""
        return self.top

    def repository(self) -> dict[str, Pattern]:
        """Every entry, in the order they were built."""
        return self.entries

    # -- Lex ---------------------------------------------------------------

    def build_tokens(self, lex: Target) -> None:
        """One entry per token `File` names, and one including them in order.

        The order is the grammar's say in which token wins where two could
        match, since TextMate takes the first pattern that matches at a
        position. The including entry is filled in place, so it is written out
        ahead of the tokens it names.
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
        scope = scope_for(classes_of(production), self.language)
        self.entries[name] = match_pattern(production, scope, self.lex_lookup)
        return name

    def lex_lookup(self, name: str) -> Production | None:
        """A `Lex` production by name, for the expressions that inline it."""
        return self.lex.productions.get(name) if self.lex is not None else None

    # -- Parse -------------------------------------------------------------

    def build_grammar(self) -> None:
        """What may appear anywhere: the bracketing entries, then the tokens.

        The brackets come first, so `(` opens its own span rather than being
        eaten by an `LParen` token of the same shape.
        """
        patterns: list[Pattern] = [
            include(self.entry_name(production))
            for production, _ in self.bracketing_productions()
        ]
        if self.lex is not None:
            patterns.append(include(TOKENS_ENTRY))
        self.entries[GRAMMAR_ENTRY] = {"patterns": patterns}

    def build_bracket_entries(self) -> None:
        """One `begin`/`end` entry per bracketing production.

        The whole span is scoped `meta.<name>`, the brackets themselves carry the
        production's own scope when it has one and a `punctuation.section` scope
        when it does not, and the body includes `grammar` — which is what makes
        the nesting recursive, and is the one thing a `match` pattern could not
        have done.
        """
        for production, (opening, closing) in self.bracketing_productions():
            scope = scope_for(classes_of(production), self.language)
            self.entries[self.entry_name(production)] = {
                "name": region_scope(production.name, self.language),
                "begin": escape_character(opening),
                "beginCaptures": {
                    "0": {
                        "name": scope
                        or punctuation_scope(production.name, self.language, "begin")
                    }
                },
                "end": escape_character(closing),
                "endCaptures": {
                    "0": {
                        "name": scope
                        or punctuation_scope(production.name, self.language, "end")
                    }
                },
                "patterns": [include(GRAMMAR_ENTRY)],
            }

    def bracketing_productions(self) -> list[tuple[Production, tuple[str, str]]]:
        """Every `Parse` production that wraps something in a fixed pair.

        Computed once and cached, and also read by the generator, which turns the
        same pairs into the bracket configuration VS Code folds and auto-closes
        with.
        """
        if self._bracketing is None:
            self._bracketing = [
                (production, pair)
                for production in self.parse_productions()
                if (pair := brackets_of(production)) is not None
            ]
        return self._bracketing

    def bracket_pairs(self) -> list[tuple[str, str]]:
        """Just the character pairs, deduplicated, for the language configuration."""
        found: list[tuple[str, str]] = []
        for _, pair in self.bracketing_productions():
            if pair not in found:
                found.append(pair)
        return found

    def parse_productions(self) -> list[Production]:
        """The `Parse` productions reachable from its `File`, `File` aside.

        A production reached across the target boundary into `Lex` is left out:
        its tokens are already matched by the `tokens` entry.
        """
        if self.parse is None:
            return []
        return reachable_productions(self.parse)

    # -- naming ------------------------------------------------------------

    def entry_name(self, production: Production) -> str:
        """The repository key a production is filed under.

        Repository keys are conventionally lower case, and two targets may name
        a production the same, so the allocator is keyed by the production's
        origin as well as its name — asking twice gives the same key back, which
        is what lets `grammar` name an entry before it is built.
        """
        wanted = snake_case(safe_identifier(production.name)) or "rule"
        return self.names.allocate(wanted, key=f"{production.origin}:{production.name}")
