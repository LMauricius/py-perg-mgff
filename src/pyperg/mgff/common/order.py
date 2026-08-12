"""The order a rule-tree backend reads items in.

An item is matched against this list top to bottom, and the first macro that
does not decline wins. The order is the specification's table of item roles, and
it is what settles every question of precedence:

    subgroup, repetition, choice             grouping.py — shapes no name may hide
    a backend's own macros                   whatever it added
    ScopeLookupPoint(name with arguments)    sep(x)by(y)
    character set                            characters.py — a-z|A-Z, outranks a name
    ScopeLookupPoint(name)                   Digit
    character                                characters.py — a, Letter, yields to a name

`ScopeLookupPoint` is not a macro but a place in the order: the grammar's own definitions
are consulted there, and the one found brings its own shape to read the call
with. Precedence therefore belongs to this list rather than to the scope chain —
a character set of several parts outranks a definition however deeply nested it
is.

The two shapes a `ScopeLookupPoint` filters with live here because that is the only thing
they are for: they match any name at all and extract nothing, since a definition
found by name reads its arguments from the item itself.

A backend adds what it recognises by handing its definitions to `extra_macros`.
They go in one band, above every name, so a backend's shape can never be hidden
by a grammar defining a macro of that name — and equally, a backend cannot
silently take a name a grammar wanted for itself.
"""

from __future__ import annotations

from ..semantics.macros import Macro, MacroDefinition, ScopeLookupPoint
from ..semantics.shapes import MacroShape
from ..semantics.signatures import (
    ARGUMENTS_PATTERN,
    NAME_PATTERN,
    extracts_nothing,
    make_shape,
)
from .characters import CHARACTER, CHARACTER_SET
from .grouping import CHOICE, REPETITION, SUBGROUP

#: The two shapes a `d` definition is looked up by.
NAME: MacroShape = make_shape("name", NAME_PATTERN, extracts_nothing)
NAME_WITH_ARGUMENTS: MacroShape = make_shape(
    "name-with-arguments", ARGUMENTS_PATTERN, extracts_nothing
)


def rule_tree_macro_order(
    extra_macros: list[MacroDefinition] | None = None,
) -> list[Macro]:
    """The order a rule-tree backend reads items in, with its own macros in it."""
    return [
        SUBGROUP,
        REPETITION,
        CHOICE,
        *(extra_macros or []),
        ScopeLookupPoint(NAME_WITH_ARGUMENTS),
        CHARACTER_SET,
        ScopeLookupPoint(NAME),
        CHARACTER,
    ]
