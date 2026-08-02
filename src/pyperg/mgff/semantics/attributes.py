"""Attributes (Part 3): the `>` lines a macro carries.

An attribute is a call with or without arguments, so `token`, `skip(false)` and
`class(Keyword Control)` all read the same way: the item's text outside the
groups is the name, and the items inside them are the arguments.

A macro written `d Head > Attributes` has no alternatives and exists only for
the attributes it carries. Naming such a macro among another macro's attributes
splices its list in, which is how a named list of attributes is reused.

What an individual attribute *means* is not decided here — that is the backend's
business. This module only reads them.
"""

from __future__ import annotations

from ...diagnostics.errors import SemanticError
from ..grammar.scope import MacroSource
from ..lexing.cst import Item, render_item


def parse_attribute(item: Item) -> tuple[str, list[str]]:
    """Read one attribute item as a name and its argument texts.

    The item's text outside the groups is the name; every item inside the groups
    is one argument, so `class(Keyword Control)` gives two.
    """
    arguments = [
        render_item(argument)
        for group in item.groups
        for line in group.lines
        for argument in line.items
    ]
    return item.text, arguments


def collect_attributes(source: MacroSource) -> dict[str, list[str]]:
    """Every attribute of a macro, with attribute-only macros spliced in.

    The `>` lines accumulate, and an attribute naming a macro that matches
    nothing contributes that macro's own attributes in its place. Repeating an
    attribute extends its argument list rather than replacing it.
    """
    collected: dict[str, list[str]] = {}
    _collect_into(source, collected, seen={source.signature})
    return collected


def _collect_into(
    source: MacroSource,
    collected: dict[str, list[str]],
    seen: set[str],
) -> None:
    """Fold one macro's attributes into the accumulator, following references.

    `seen` holds the signatures already on the splice path, so a list that names
    itself is reported rather than followed forever.
    """
    for item in source.attributes:
        name, arguments = parse_attribute(item)
        # An argument-less attribute naming an attribute-only macro is a
        # reference to a named list, not an attribute of its own.
        referenced = source.scope.lookup_source(name) if not arguments else None
        if referenced is not None and referenced.matches_nothing:
            if referenced.signature in seen:
                raise SemanticError(
                    f"attribute list {name!r} refers to itself", item.span
                )
            _collect_into(referenced, collected, seen | {referenced.signature})
            continue
        existing = collected.setdefault(name, [])
        existing.extend(argument for argument in arguments if argument not in existing)
