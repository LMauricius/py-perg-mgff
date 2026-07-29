"""Macro expansion (Part 2).

Not implemented yet.

Expansion is capture-free substitution: each occurrence of a parameter in the
body is replaced by its argument, a multi-item argument being wrapped in a group
so its grouping survives.

    sep(Ident = Expr)by(,)   =>   (Ident = Expr) ( , (Ident = Expr) )*

Macros may be self-referencing or mutually recursive, so calls are expanded on
demand and never exhaustively.
"""

from __future__ import annotations

from ..mgff.ast import Macro
from ..mgff.cst import Item


def expand_call(macro: Macro, arguments: list[list[Item]]) -> list[list[Item]]:
    """Expand one call into the macro's alternatives, with arguments substituted.

    Returns one item sequence per alternative. Raises `SemanticError` when the
    argument count does not match the macro's parameters.
    """
    raise NotImplementedError


def substitute(items: list[Item], bindings: dict[str, list[Item]]) -> list[Item]:
    """Replace parameter occurrences in an item sequence.

    A parameter appearing as bare text becomes its argument; a multi-item
    argument is wrapped in a group. Substitution descends into groups, and the
    bindings of an inner macro shadow nothing, since expansion is capture-free.
    """
    raise NotImplementedError
