"""Rule trees as TextMate patterns.

Where Kate offers a dozen ways to match text and the backend picks the cheapest,
TextMate offers exactly one: an Oniguruma regular expression. So there is no
table here, and no fusing of literals to reach a cheaper rule — a production
becomes **one** pattern holding one expression, which is both the fastest thing
TextMate can do and the most readable output.

    {"match": "[0-9]+(?:\\.[0-9]+)?", "name": "constant.numeric.float.toy"}

Two things the expression must say that the rule tree does not:

- **Word boundaries.** Kate's `keyword` and `WordDetect` rules match only
  between word boundaries; TextMate has no such rule, so a production whose
  alternatives are all plain words is wrapped in `\\b…\\b`. Without it `if`
  would match inside `iffy`.
- **Longest match.** `utils.regex.alternation` already orders a `|` choice
  longest fixed option first, which is what makes `<=` win over `<`.

A production that reaches itself has no regular form. TextMate can still express
it — a `begin`/`end` pattern is a pushdown machine, the same one Kate's contexts
are — but not as a `match`, so that case belongs to `repository`.
"""

from __future__ import annotations

from ...diagnostics.errors import GeneratorError
from ...mgff.common.rules import Rule
from ...mgff.semantics.model import Production
from ..utils.regex import Lookup, regex_of
from ..utils.walk import flatten, fuse_literals, literal_of, nullable
from ..utils.words import is_word

#: A pattern object as it appears in the generated JSON.
Pattern = dict[str, object]


def include(name: str) -> Pattern:
    """A reference to a repository entry."""
    # {"include": f"#{name}"}


def word_alternatives(production: Production) -> list[str] | None:
    """The production's alternatives as plain words, or None if they are not.

    This is the same test Kate uses to build a `<list>`, and it is asked for the
    same reason: a fixed word must not match inside a longer one.
    """
    # fuse each alternative's single-character run into a string, then require
    # every one of them to be a word


def keyword_pattern(words: list[str]) -> str:
    """A choice of fixed words, bounded so none matches inside a longer word."""
    # r"\b(?:" + "|".join(escaped words, longest first) + r")\b"


def regex_for(production: Production, lookup: Lookup) -> str:
    """A whole production as one expression.

    Raises `GeneratorError` when it has no regular form, which for a `match`
    pattern means a production that reaches itself.
    """
    # 1. word_alternatives -> keyword_pattern, which regex_of cannot produce
    # 2. otherwise regex_of over production.rule
    # 3. None -> GeneratorError naming the production


def match_pattern(production: Production, scope: str | None, lookup: Lookup) -> Pattern:
    """A production as one `match` pattern, scoped by its classes.

    An unscoped pattern is still emitted: it consumes the text it matches, which
    is how a token is kept from being read as something else.
    """
    # {"match": regex_for(...)} plus "name" when scope is not None


def matches_nothing(production: Production, lookup: Lookup) -> bool:
    """Whether the production's expression could match the empty string.

    A zero-width `match` makes no progress, and while VS Code's tokeniser
    survives one it will never highlight anything, so the caller says so rather
    than emitting a rule that silently does nothing.
    """
    # nullable(production.rule, lookup)
