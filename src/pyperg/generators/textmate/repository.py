"""Building a TextMate grammar's repository from the `Lex` and `Parse` targets.

TextMate highlights with a stack of **patterns**. A `match` pattern consumes
what it matched; a `begin`/`end` pattern pushes, matches its own `patterns`
until the `end` expression fires, and pops. That is a pushdown machine over
text, exactly like Kate's contexts, so the two backends read a grammar the same
way and differ only in how they spell the answer.

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

from ...mgff.semantics.model import GrammarModel, Production, Target
from ..utils.classes import classes_of
from ..utils.naming import NameAllocator, safe_identifier, snake_case
from .patterns import Pattern
from .scopes import scope_for

#: The macro both targets start at.
START_PRODUCTION = "File"

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
        # the two targets, the entry name allocator seeded with the reserved
        # names above, the repository being filled in, and the cached bracketing
        # analysis — the top patterns and the entries must agree on it
        ...

    # -- the whole grammar -------------------------------------------------

    def build(self) -> None:
        """Build every repository entry, and the patterns a document starts in.

        A grammar with a `Parse` target starts at `grammar`, which reaches
        everything; one with only tokens starts at `tokens`.
        """
        # Parse present -> grammar entry, then one entry per bracketing production
        # Lex present   -> tokens entry, then one entry per token production
        # top patterns  -> include grammar, or include tokens when there is no Parse

    def top_patterns(self) -> list[Pattern]:
        """What a document is matched against before anything has been pushed."""

    def repository(self) -> dict[str, Pattern]:
        """Every entry, in the order they were built."""

    # -- Lex ---------------------------------------------------------------

    def build_tokens(self, lex: Target) -> None:
        """One entry per token `File` names, and one including them in order.

        The order is the grammar's say in which token wins where two could
        match, since TextMate takes the first pattern that matches at a
        position.
        """
        # for each name in token_order(lex): entry_for_token, collecting includes

    def entry_for_token(self, production: Production) -> str:
        """One token production as its own `match` entry; returns the entry name.

        A production whose expression could match nothing is skipped with a note
        on standard error: a zero-width pattern never highlights anything.
        """

    # -- Parse -------------------------------------------------------------

    def build_grammar(self) -> None:
        """What may appear anywhere: the bracketing entries, then the tokens.

        The brackets come first, so `(` opens its own span rather than being
        eaten by an `LParen` token of the same shape.
        """

    def build_bracket_entries(self) -> None:
        """One `begin`/`end` entry per bracketing production.

        The whole span is scoped `meta.<name>`, the brackets themselves carry
        the production's own scope when it has one and a `punctuation.section`
        scope when it does not, and the body includes `grammar`, which is what
        makes the nesting recursive.
        """

    def bracketing_productions(self) -> list[tuple[Production, tuple[str, str]]]:
        """Every `Parse` production that wraps something in a fixed pair.

        Computed once and cached, and also read by the generator, which turns the
        same pairs into the bracket configuration VS Code folds and auto-closes
        with.
        """

    def parse_productions(self) -> list[Production]:
        """The `Parse` productions reachable from its `File`, `File` aside.

        A production reached across the target boundary into `Lex` is left out:
        its tokens are already matched by the `tokens` entry.
        """

    # -- naming ------------------------------------------------------------

    def entry_name(self, production: Production) -> str:
        """The repository key a production is filed under.

        Repository keys are conventionally lower case, and two targets may name
        a production the same, so the allocator is keyed by the production's
        origin as well as its name.
        """
