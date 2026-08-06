"""Attributes (Part 3): the `>` lines a macro carries.

An attribute is a call with or without arguments, so `token`, `skip(false)` and
`class(Keyword Control)` all read the same way: the item's text outside the
groups is the name, and the items inside them are the arguments.

A macro written `d Head > Attributes` has no alternatives and exists only for
the attributes it carries. Naming such a macro among another macro's attributes
splices its list in, which is how a named list of attributes is reused.

A **scope** carries attributes too — the `>` lines at its top — and they are read
the same way, from the scope itself outwards, so a file and a target may reuse
the very same named lists a macro does.

What an individual attribute *means* is not decided here — that is the backend's
business. This module only reads them.
"""

from __future__ import annotations

from ...diagnostics.errors import SemanticError
from ..grammar.scope import MacroSource, Scope
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
    _collect_into(source.attributes, source.scope, collected, seen={source.signature})
    return collected


def collect_scope_attributes(scope: Scope) -> dict[str, list[str]]:
    """Every attribute a scope carries, read the way a macro's are.

    A named list is looked up from the scope itself, so a target may reuse one
    written outside it and the file scope may reuse one of its own.
    """
    collected: dict[str, list[str]] = {}
    _collect_into(scope.attributes, scope, collected, seen=set())
    return collected


def _collect_into(
    attributes: list[Item],
    scope: Scope,
    collected: dict[str, list[str]],
    seen: set[str],
) -> None:
    """Fold one list of attributes into the accumulator, following references.

    `scope` is where a named list is looked up from. `seen` holds the signatures
    already on the splice path, so a list that names itself is reported rather
    than followed forever.
    """
    for item in attributes:
        name, arguments = parse_attribute(item)
        # An argument-less attribute naming an attribute-only macro is a
        # reference to a named list, not an attribute of its own.
        referenced = scope.lookup_source(name) if not arguments else None
        if referenced is not None and referenced.matches_nothing:
            if referenced.signature in seen:
                raise SemanticError(
                    f"attribute list {name!r} refers to itself", item.span
                )
            _collect_into(
                referenced.attributes,
                referenced.scope,
                collected,
                seen | {referenced.signature},
            )
            continue
        existing = collected.setdefault(name, [])
        existing.extend(argument for argument in arguments if argument not in existing)
