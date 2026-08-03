"""The rule tree a production's alternatives are built from.

Five rule kinds, of which only two are named by MGFF itself:

    Sequence     items matched one after another
    Repetition   a body matched a number of times
    Choice       one of several options, order- or length-based
    Reference    another production of the same target
    MacroCall    a call whose macro builds no rule of its own

`Repetition` and `Choice` are here because every generator needs them and the
model may as well name them. A macro with nothing to add to that vocabulary —
a character set, or whatever a backend defines — produces a `MacroCall`, which
names the macro, keeps the item unchanged and leaves the reading of it to
whoever defined the macro.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..grammar.macros import MacroDefinition
from ..lexing.cst import Item


@dataclass(slots=True)
class Sequence:
    """Items matched one after another. An empty sequence matches nothing."""

    items: list["Rule"] = field(default_factory=list)


@dataclass(slots=True)
class Repetition:
    """A body matched between `minimum` and `maximum` times, `None` for no limit."""

    body: "Rule"
    minimum: int
    maximum: int | None
    marker: str  # `+`, `*` or `?`, kept for round-tripping and messages


@dataclass(slots=True)
class Choice:
    """One of several options.

    `symbol` is `/` when the first option that succeeds wins and `|` when the
    longest match wins.
    """

    options: list["Rule"]
    symbol: str


@dataclass(slots=True)
class Reference:
    """A call on another production of the same target.

    `name` is how the production is named inside its target, which is also the
    key it is filed under in `Target.productions`.
    """

    name: str


@dataclass(slots=True)
class MacroCall:
    """A call kept as the item it was written as, for its macro to read back.

    `macro` is the definition that built it, and identifies it: whoever defined
    the macro checks `node.macro is MINE`, so no two backends can collide over a
    name. `arguments` holds whatever sub-rules the call carries; a character set
    has none, while a capture group has the rule it wraps.
    """

    macro: MacroDefinition
    item: Item
    arguments: list["Rule"] = field(default_factory=list)


Rule = Sequence | Repetition | Choice | Reference | MacroCall
