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
from ...mgff.semantics.model import Production
from ..utils.regex import Lookup, alternation, concatenation, escape_character, regex_of
from ..utils.walk import literal_of, nullable
from ..utils.words import is_word

#: A pattern object as it appears in the generated JSON.
Pattern = dict[str, object]


def include(name: str) -> Pattern:
    """A reference to a repository entry."""
    return {"include": f"#{name}"}


def word_alternatives(production: Production) -> list[str] | None:
    """The production's alternatives as plain words, or None if they are not.

    This is the same test Kate uses to build a `<list>`, and it is asked for the
    same reason: a fixed word must not match inside a longer one. Unlike Kate it
    is asked of a single alternative too, since `\\b` costs nothing where Kate
    would have had to pay for a slower rule.
    """
    words: list[str] = []
    for alternative in production.alternatives:
        literal = literal_of(alternative)
        if literal is None or not is_word(literal):
            return None
        words.append(literal)
    return words or None


def keyword_pattern(words: list[str], symbol: str) -> str:
    """A choice of fixed words, bounded so none matches inside a longer word.

    The boundaries also repair an order-based choice: `\\b(?:if|iffy)\\b` still
    matches `iffy` whole, because `if` cannot end in the middle of a word.
    """
    options = [concatenation([escape_character(char) for char in word]) for word in words]
    return r"\b" + alternation(options, symbol) + r"\b"


def regex_for(production: Production, lookup: Lookup) -> str:
    """A whole production as one expression.

    Raises `GeneratorError` when it has no regular form, which for a `match`
    pattern means a production that reaches itself.
    """
    if not production.alternatives:
        raise GeneratorError(f"production {production.name!r} matches nothing")

    words = word_alternatives(production)
    if words is not None:
        return keyword_pattern(words, production.choice_symbol or "/")

    pattern = regex_of(production.rule, lookup)
    if pattern is None:
        raise GeneratorError(
            f"the token {production.name!r} reaches itself, so no single pattern "
            "can match it; TextMate matches text with expressions, which cannot "
            "recurse. Only a bracketing `Parse` production nests"
        )
    return pattern


def match_pattern(production: Production, scope: str | None, lookup: Lookup) -> Pattern:
    """A production as one `match` pattern, scoped by its classes.

    An unscoped pattern is still emitted: it consumes the text it matched, which
    is what keeps a token from being read as something else.
    """
    pattern: Pattern = {}
    if scope is not None:
        pattern["name"] = scope
    pattern["match"] = regex_for(production, lookup)
    return pattern


def matches_nothing(production: Production, lookup: Lookup) -> bool:
    """Whether the production's expression could match the empty string.

    A zero-width `match` makes no progress. VS Code's tokeniser survives one, but
    the rule can never highlight anything, so the caller says so rather than
    emitting a pattern that silently does nothing.
    """
    return nullable(production.rule, lookup)
