"""Macro expansion (Part 2).

Expansion is capture-free substitution: each occurrence of a parameter in the
body is replaced by its argument, a multi-item argument being wrapped in a group
so its grouping survives.

    sep(Ident = Expr)by(,)   =>   (Ident = Expr) ( , (Ident = Expr) )*

Macros may be self-referencing or mutually recursive, so calls are expanded on
demand and never exhaustively.
"""

from __future__ import annotations

from ..diagnostics.errors import SemanticError
from ..diagnostics.span import Span
from ..mgff.cst import Group, Item, Line, Text
from .scope import Macro


def arguments_of(item: Item) -> list[list[Item]]:
    """The argument of each group of a call, as a sequence of items.

    A group's lines are joined, since the line breaks inside a group are layout.
    """
    return [
        [argument for line in group.lines for argument in line.items]
        for group in item.groups
    ]


def wrap_in_group(items: list[Item], span: Span) -> Item:
    """Make a one-group item holding a sequence, so its grouping survives.

    A single item needs no wrapping; anything else becomes `( … )` and is read
    back as a subgroup.
    """
    if len(items) == 1:
        return items[0]
    return Item(span=span, parts=[Group(span=span, lines=[Line(span=span, items=items)])])


def expand_call(macro: Macro, arguments: list[list[Item]]) -> list[list[Item]]:
    """Expand one call into the macro's alternatives, with arguments substituted.

    Returns one item sequence per alternative. Raises `SemanticError` when the
    argument count does not match the macro's parameters.
    """
    if len(arguments) != len(macro.parameters):
        raise SemanticError(
            f"macro {macro.signature!r} takes {len(macro.parameters)} argument(s), "
            f"{len(arguments)} given",
            macro.span,
        )
    bindings = dict(zip(macro.parameters, arguments))
    return [substitute(option, bindings) for option in macro.options]


def substitute(items: list[Item], bindings: dict[str, list[Item]]) -> list[Item]:
    """Replace parameter occurrences in an item sequence.

    A parameter appearing as bare text becomes its argument; a multi-item
    argument is wrapped in a group. Substitution descends into groups, and the
    bindings of an inner macro shadow nothing, since expansion is capture-free.
    """
    return [_substitute_item(item, bindings) for item in items]


def _substitute_item(item: Item, bindings: dict[str, list[Item]]) -> Item:
    """Substitute inside one item, rebuilding it only where something changed."""
    # A bare parameter name is replaced whole; anything else keeps its shape and
    # is rewritten part by part.
    if item.is_bare_text and item.text in bindings:
        return wrap_in_group(bindings[item.text], item.span)

    parts: list[Text | Group] = []
    for part in item.parts:
        if isinstance(part, Text):
            parts.append(part)
        else:
            parts.append(_substitute_group(part, bindings))
    return Item(span=item.span, parts=parts)


def _substitute_group(group: Group, bindings: dict[str, list[Item]]) -> Group:
    """Substitute inside every line of a group."""
    return Group(
        span=group.span,
        lines=[
            Line(span=line.span, items=substitute(line.items, bindings))
            for line in group.lines
        ],
    )
