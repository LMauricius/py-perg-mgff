"""Grouping, repetition and choice: the shapes written with brackets.

    ( … )           SUBGROUP     one rule out of several items
    ( R )+ * ?      REPETITION   a body matched a number of times
    (A)|(B)  (A)/(B)  CHOICE     one of several options

None of the three can be hidden by a name, since a grammar cannot define a macro
whose signature is bare brackets. They sit at the very top of the order.

A group reaches these already produced: the resolver reads it as a rule before
the call is made, so nothing here touches the resolver, and the context every
`produce_call` receives goes unread.
"""

from __future__ import annotations

import re

from ..semantics.macros import MacroDefinition
from ..semantics.shapes import MacroShape
from ..semantics.signatures import make_shape
from ..itemizing.cst import Item
from ..systems.context import CallContext
from .rules import Choice, Rule, Repetition

#: How many times each marker repeats its body.
REPETITION_MARKERS: dict[str, tuple[int, int | None]] = {
    "+": (1, None),  # one or more
    "*": (0, None),  # zero or more
    "?": (0, 1),  # optional
}

#: The two choice separators: length-based, and order-based.
CHOICE_MARKERS: frozenset[str] = frozenset({"|", "/"})


# -- what each call carries -------------------------------------------------


def _subgroup_call_arguments(item: Item, match: re.Match[str]) -> dict[str, object]:
    return {"body": item.groups[0]}


def _repetition_call_arguments(item: Item, match: re.Match[str]) -> dict[str, object]:
    return {"body": item.groups[0], "marker": match["marker"]}


def _choice_call_arguments(item: Item, match: re.Match[str]) -> dict[str, object]:
    return {"options": item.groups, "symbol": match["symbol"]}


# -- the shapes -------------------------------------------------------------

SUBGROUP_SHAPE: MacroShape = make_shape("subgroup", r"\(\)", _subgroup_call_arguments)

REPETITION_SHAPE: MacroShape = make_shape(
    "repetition", r"\(\)(?P<marker>[+*?])", _repetition_call_arguments
)

#: The separators must all be the same one, which is what the backreference says.
CHOICE_SHAPE: MacroShape = make_shape(
    "choice", r"\(\)(?P<symbol>[|/])\(\)(?:(?P=symbol)\(\))*", _choice_call_arguments
)


# -- what they produce ------------------------------------------------------


def _subgroup(context: CallContext, body: Rule) -> Rule:
    """`( … )`: the group's own lines, joined into one rule."""
    return body


def _repetition(context: CallContext, body: Rule, marker: str) -> Rule:
    """`( R )+`, `( R )*`, `( R )?`."""
    minimum, maximum = REPETITION_MARKERS[marker]
    return Repetition(body, minimum, maximum, marker)


def _choice(context: CallContext, options: list[Rule], symbol: str) -> Rule:
    """`(O1)|(O2)|…` and `(O1)/(O2)/…`, an inline choice."""
    return Choice(options, symbol)


SUBGROUP = MacroDefinition(shape=SUBGROUP_SHAPE, produce_call=_subgroup)
REPETITION = MacroDefinition(shape=REPETITION_SHAPE, produce_call=_repetition)
CHOICE = MacroDefinition(shape=CHOICE_SHAPE, produce_call=_choice)
