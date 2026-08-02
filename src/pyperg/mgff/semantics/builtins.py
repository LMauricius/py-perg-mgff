"""The macros every rule-tree backend starts with, and attributes (Part 3).

Each is a `MacroDefinition`: a shape saying which calls it answers to, and a
`produce_call` saying what such a call produces — here, a node of a rule tree.
The parameters of each function are the keys its shape extracts, so the two read
as one thing.

The order below is the specification's table of item roles, read top to bottom.
`Scoped` marks the two points at which the grammar's own definitions are
consulted, and everything between them is what outranks or yields to a name:

    subgroup, repetition, choice   shapes no name may hide
    Scoped(name with arguments)    sep(x)by(y)
    character set                  a-z|A-Z, which outranks a name
    Scoped(name)                   Digit
    character                      a, Letter, which yields to a name

Attributes live here too. An attribute is a call with or without arguments, so
`token`, `skip(false)` and `class(Keyword Control)` all read the same way: the
item's text is the name, and the items inside its groups are the arguments.

A macro written `d Head > Attributes` has no alternatives and exists only for
the attributes it carries. Naming such a macro among another macro's attributes
splices its list in, which is how a named list of attributes is reused.
"""

from __future__ import annotations

from ...diagnostics.errors import SemanticError
from ..grammar import shapes
from ..grammar.macros import Macro, MacroDefinition, Scoped
from ..grammar.scope import MacroSource
from ..lexing.cst import Item, render_item
from .charset import CHARACTER, CHARACTER_SET
from .nodes import Choice, Node, Repetition

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


# -- what the built-in shapes produce --------------------------------------
#
# A group reaches these already produced: the resolver reads it as a rule before
# the call is made, so nothing here needs the resolver itself.


def _subgroup(body: Node) -> Node:
    """`( … )`: the group's own lines, joined into one rule."""
    return body


def _repetition(body: Node, marker: str) -> Node:
    """`( R )+`, `( R )*`, `( R )?`."""
    minimum, maximum = REPETITION_MARKERS[marker]
    return Repetition(body, minimum, maximum, marker)


def _choice(options: list[Node], symbol: str) -> Node:
    """`(O1)|(O2)|…` and `(O1)/(O2)/…`, an inline choice."""
    return Choice(options, symbol)


SUBGROUP = MacroDefinition(shape=shapes.SUBGROUP, produce_call=_subgroup)
REPETITION = MacroDefinition(shape=shapes.REPETITION, produce_call=_repetition)
CHOICE = MacroDefinition(shape=shapes.CHOICE, produce_call=_choice)


def rule_tree_macros() -> list[Macro]:
    """The order a rule-tree backend reads items in, before it adds its own."""
    return [
        SUBGROUP,
        REPETITION,
        CHOICE,
        Scoped(shapes.NAME_WITH_ARGUMENTS),
        CHARACTER_SET,
        Scoped(shapes.NAME),
        CHARACTER,
    ]


# -- attributes ------------------------------------------------------------


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
