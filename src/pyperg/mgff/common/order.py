"""The order a rule-tree backend reads items in.

An item is matched against this list top to bottom, and the first macro that
does not decline wins. The order is the specification's table of item roles, and
it is what settles every question of precedence:

    subgroup, repetition, choice   grouping.py — shapes no name may hide
    a backend's own macros         whatever it added
    Scoped(name with arguments)    sep(x)by(y)
    character set                  characters.py — a-z|A-Z, outranks a name
    Scoped(name)                   Digit
    character                      characters.py — a, Letter, yields to a name

`Scoped` is not a macro but a place in the order: the grammar's own definitions
are consulted there, and the one found brings its own shape to read the call
with. Precedence therefore belongs to this list rather than to the scope chain —
a character set of several parts outranks a definition however deeply nested it
is.

The two shapes a `Scoped` filters with live here because that is the only thing
they are for: they match any name at all and extract nothing, since a definition
found by name reads its arguments from the item itself.

A backend adds what it recognises by handing its definitions to `extra_macros`.
They go in one band, above every name, so a backend's shape can never be hidden
by a grammar defining a macro of that name — and equally, a backend cannot
silently take a name a grammar wanted for itself.
"""

from __future__ import annotations

from ..grammar.macros import Macro, MacroDefinition, Scoped
from ..grammar.shapes import MacroShape
from ..grammar.signatures import ARGUMENTS_PATTERN, NAME_PATTERN, no_args, shape
from .characters import CHARACTER, CHARACTER_SET
from .grouping import CHOICE, REPETITION, SUBGROUP

#: The two shapes a `d` definition is looked up by.
NAME: MacroShape = shape("name", NAME_PATTERN, no_args)
NAME_WITH_ARGUMENTS: MacroShape = shape(
    "name-with-arguments", ARGUMENTS_PATTERN, no_args
)


def rule_tree_macros(extra_macros: list[MacroDefinition] | None = None) -> list[Macro]:
    """The order a rule-tree backend reads items in, with its own macros in it."""
    return [
        SUBGROUP,
        REPETITION,
        CHOICE,
        *(extra_macros or []),
        Scoped(NAME_WITH_ARGUMENTS),
        CHARACTER_SET,
        Scoped(NAME),
        CHARACTER,
    ]
