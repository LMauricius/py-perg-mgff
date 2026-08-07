"""Where a highlighter starts, and in what order it tries the tokens.

A syntax highlighter is a pushdown machine over text whichever format it is
written in, and the machine itself is derived in `machine`. What is left here is
what both backends ask before that: which macro a target starts at, and the
order `Lex` wants its tokens tried in where a context holds several of them.

The one question that *is* format-specific — how to spell a match — is not here.
"""

from __future__ import annotations

from ...diagnostics.errors import GeneratorError
from ...mgff.semantics.model import Production, Target
from .walk import referenced_production_names

#: The macro a target starts at. Every highlighting backend begins there.
START_PRODUCTION = "File"


def start_production_of(target: Target) -> Production:
    """A target's `File` production, which is where generation begins."""
    production = target.productions.get(START_PRODUCTION)
    if production is None:
        raise GeneratorError(
            f"target {target.name!r} has no `{START_PRODUCTION}` macro; "
            f"highlighting starts there. Write `d {START_PRODUCTION} = …` "
            "listing what the target matches."
        )
    return production


def token_names_in_order(target: Target) -> list[str]:
    """The token productions `File` names, in the order they were written.

    A highlighter takes the first rule that matches, so this order is the
    grammar's say in which token wins where two could match. Only the
    productions `File` names are tokens; the rest are helpers, inlined into the
    expressions that use them.
    """
    ordered: list[str] = []
    for name in referenced_production_names(start_production_of(target).rule):
        if name not in ordered and name in target.productions:
            ordered.append(name)
    if not ordered:
        raise GeneratorError(
            f"`{START_PRODUCTION}` of target {target.name!r} names no productions; "
            "it should list the tokens, as in `d File = ( Ident / Number / Space )*`"
        )
    return ordered
