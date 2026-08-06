"""What a match *is*, said in a way no backend owns.

A class is a match's identity. `class(…)` names it outright and `autoclass` takes
the macro's own name, which is the common case where the name already says what
the match is:

    d LParen = \\(
             > class(\\() style(Normal)

    d Comment = # ( AnyChar )*
              > autoclass style(Comment)

Classes are free text. Nothing here validates them, because nothing here decides
what they are for: a later phase reading a list of matches — see `utils.pipeline`
— matches its terminals against them, so a class is whatever the grammar wants to
say a match may be recognised by. `class(Float Number Literal)` says a number is
all three, and a later phase naming any one of them finds it.

How a match should *look* is a different question, and `utils.styles` answers it.
"""

from __future__ import annotations

from ...diagnostics.errors import GeneratorError
from ...mgff.semantics.model import Production


def classes_of(production: Production) -> list[str]:
    """The classes a production's match carries, empty when it carries none.

    `class(…)` names them outright; `autoclass` takes the macro's own name,
    verbatim. A production asking for neither is unclassed, and nothing but its
    name can reach it.
    """
    if "class" in production.attributes:
        classes = production.attributes["class"]
        if not classes:
            raise GeneratorError(
                f"`class` on {production.name!r} needs at least one class, "
                "as in `> class(Keyword)`"
            )
        return classes
    if "autoclass" in production.attributes:
        return [production.name]
    return []
