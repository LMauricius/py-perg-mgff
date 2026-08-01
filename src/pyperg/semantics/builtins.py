"""Built-in macros and attributes (Part 3).

These are macros whose expansion is defined by the generator rather than by
MGFF. Every target that treats macros as matching rules provides the repetition
and choice forms; a domain-specific dialect may add built-ins of its own.

Attributes live here too. An attribute is a call with or without arguments, so
`token`, `skip(false)` and `class(Keyword Control)` all read the same way: the
item's text is the name, and the items inside its groups are the arguments.

A macro written `d Head > Attributes` has no alternatives and exists only for
the attributes it carries. Naming such a macro among another macro's attributes
splices its list in, which is how a named list of attributes is reused.
"""

from __future__ import annotations

from ..diagnostics.errors import SemanticError
from ..grammar.scope import Macro
from ..mgff.cst import Item, render_item

# Rule-matching built-ins, present in every target with productions.
REPETITION_MARKERS: dict[str, tuple[int, int | None]] = {
    "+": (1, None),  # one or more
    "*": (0, None),  # zero or more
    "?": (0, 1),  # optional
}

CHOICE_MARKERS: frozenset[str] = frozenset({"|", "/"})  # length-based, order-based

# Attributes the established targets understand. Their meaning is
# generator-specific, and a backend adds the names it recognises to this base.
KNOWN_ATTRIBUTES: frozenset[str] = frozenset({"token", "skip", "string"})


def is_builtin(name: str) -> bool:
    """Whether a name is provided by the generator rather than by the grammar.

    The rule-matching built-ins are shapes rather than names, so the only names
    reserved to the generator are the markers that spell them.
    """
    return name in REPETITION_MARKERS or name in CHOICE_MARKERS


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


def collect_attributes(macro: Macro) -> dict[str, list[str]]:
    """Every attribute of a macro, with attribute-only macros spliced in.

    The `>` lines accumulate, and an attribute naming a macro that matches
    nothing contributes that macro's own attributes in its place. Repeating an
    attribute extends its argument list rather than replacing it.
    """
    collected: dict[str, list[str]] = {}
    _collect_into(macro, collected, seen={macro.signature})
    return collected


def _collect_into(
    macro: Macro,
    collected: dict[str, list[str]],
    seen: set[str],
) -> None:
    """Fold one macro's attributes into the accumulator, following references.

    `seen` holds the signatures already on the splice path, so a list that names
    itself is reported rather than followed forever.
    """
    for item in macro.attributes:
        name, arguments = parse_attribute(item)
        # An argument-less attribute naming an attribute-only macro is a
        # reference to a named list, not an attribute of its own.
        referenced = macro.scope.lookup(name) if not arguments else None
        if referenced is not None and referenced.matches_nothing:
            if referenced.signature in seen:
                raise SemanticError(
                    f"attribute list {name!r} refers to itself", item.span
                )
            _collect_into(referenced, collected, seen | {referenced.signature})
            continue
        existing = collected.setdefault(name, [])
        existing.extend(argument for argument in arguments if argument not in existing)
