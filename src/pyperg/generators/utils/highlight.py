"""What a highlighter reads out of a resolved grammar.

A syntax highlighter is a pushdown machine over text, whichever format it is
written in, so every highlighting backend asks a grammar the same three
questions: where does it start, in what order are the tokens tried, and what
nests. The answers do not depend on the output format, so they live here and
Kate and TextMate both read them.

The one question that *is* format-specific — how to spell a match — is not here.
"""

from __future__ import annotations

from ...diagnostics.errors import GeneratorError
from ...mgff.semantics.model import Production, Target
from .graph import reachable_from, reference_graph
from .walk import flatten, fuse_literals, references, single_character

#: The macro a target starts at. Every highlighting backend begins there.
START_PRODUCTION = "File"


def start_of(target: Target) -> Production:
    """A target's `File` production, which is where generation begins."""
    production = target.productions.get(START_PRODUCTION)
    if production is None:
        raise GeneratorError(
            f"target {target.name!r} has no `{START_PRODUCTION}` macro; "
            f"highlighting starts there. Write `d {START_PRODUCTION} = …` "
            "listing what the target matches."
        )
    return production


def token_order(target: Target) -> list[str]:
    """The token productions `File` names, in the order they were written.

    A highlighter takes the first rule that matches, so this order is the
    grammar's say in which token wins where two could match. Only the
    productions `File` names are tokens; the rest are helpers, inlined into the
    expressions that use them.
    """
    ordered: list[str] = []
    for name in references(start_of(target).rule):
        if name not in ordered and name in target.productions:
            ordered.append(name)
    if not ordered:
        raise GeneratorError(
            f"`{START_PRODUCTION}` of target {target.name!r} names no productions; "
            "it should list the tokens, as in `d File = ( Ident / Number / Space )*`"
        )
    return ordered


def brackets_of(production: Production) -> tuple[str, str] | None:
    """The fixed opening and closing characters a production wraps things in.

    This is the part of a grammar a pushdown machine can genuinely reproduce: an
    alternative of one item brackets nothing and is ignored; every alternative
    that holds more must open and close with the same pair, or the production is
    not a bracketing one.
    """
    found: tuple[str, str] | None = None
    for alternative in production.alternatives:
        parts = fuse_literals(flatten(alternative))
        if len(parts) < 2:
            continue
        opening = single_character(parts[0])
        closing = single_character(parts[-1])
        if opening is None or closing is None:
            return None
        if found is not None and found != (opening, closing):
            return None
        found = (opening, closing)
    return found


def reachable_productions(target: Target) -> list[Production]:
    """The target's own productions reachable from its `File`, `File` aside.

    A production reached across a target boundary keeps the origin it was
    written in, and is left out here: an earlier target has already matched it.
    Empty when the target names no `File` at all, since then it describes no
    structure to walk.
    """
    graph = reference_graph(target.productions)
    reachable = reachable_from(START_PRODUCTION, graph)
    return [
        production
        for name, production in target.productions.items()
        if name in reachable
        and name != START_PRODUCTION
        and production.origin == target.name
    ]
