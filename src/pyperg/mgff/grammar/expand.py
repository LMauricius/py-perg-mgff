"""Macro expansion (Part 2).

Expansion is capture-free substitution: each occurrence of a parameter in the
body is replaced by its argument, a multi-item argument being wrapped in a group
so its grouping survives.

    sep(Ident = Expr)by(,)   =>   (Ident = Expr) ( , (Ident = Expr) )*

Macros may be self-referencing or mutually recursive, so calls are expanded on
demand and never exhaustively.

The arguments arrive already bound to their parameters: a definition's shape
reads a call by the head it was written with, so `sep(a)by(,)` reaches the
definition as `R` and `S` and there is no arity to check here.
"""

from __future__ import annotations

from ...diagnostics.span import Span
from ..lexing.cst import Group, Item, Line, Text, call_arguments_of

__all__ = [
    "call_arguments_of",
    "expand_alternatives",
    "substitute_parameters",
    "wrap_items_in_group",
]


def wrap_items_in_group(items: list[Item], span: Span) -> Item:
    """Make a one-group item holding a sequence, so its grouping survives.

    A single item needs no wrapping; anything else becomes `( … )` and is read
    back as a subgroup.
    """
    if len(items) == 1:
        return items[0]
    return Item(
        span=span, parts=[Group(span=span, lines=[Line(span=span, items=items)])]
    )


def expand_alternatives(
    options: list[list[Item]], bindings: dict[str, list[Item]]
) -> list[list[Item]]:
    """Expand a definition's alternatives, with the call's arguments substituted.

    Returns one item sequence per alternative.
    """
    return [substitute_parameters(option, bindings) for option in options]


def substitute_parameters(
    items: list[Item], bindings: dict[str, list[Item]]
) -> list[Item]:
    """Replace parameter occurrences in an item sequence.

    A parameter appearing as bare text becomes its argument; a multi-item
    argument is wrapped in a group. Substitution descends into groups, and the
    bindings of an inner macro shadow nothing, since expansion is capture-free.
    """
    return [_substitute_in_item(item, bindings) for item in items]


def _substitute_in_item(item: Item, bindings: dict[str, list[Item]]) -> Item:
    """Substitute inside one item, rebuilding it only where something changed."""
    # A bare parameter name is replaced whole; anything else keeps its shape and
    # is rewritten part by part.
    if item.is_bare_text and item.text in bindings:
        return wrap_items_in_group(bindings[item.text], item.span)

    parts: list[Text | Group] = []
    for part in item.parts:
        if isinstance(part, Text):
            parts.append(part)
        else:
            parts.append(_substitute_in_group(part, bindings))
    return Item(span=item.span, parts=parts)


def _substitute_in_group(group: Group, bindings: dict[str, list[Item]]) -> Group:
    """Substitute inside every line of a group."""
    return Group(
        span=group.span,
        lines=[
            Line(span=line.span, items=substitute_parameters(line.items, bindings))
            for line in group.lines
        ],
    )
