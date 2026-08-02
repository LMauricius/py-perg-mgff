"""Macro shapes: the name-patterns a call may be recognised by.

MGFF has one kind of item — a call — and a macro is whatever answers to it. A
macro's *name* is therefore a pattern rather than a fixed string: the expression
below is matched against the item's **signature**, its text with the groups
emptied, so `( Digit )+` gives `()+` and `sep(x)by(y)` gives `sep()by()`.

A shape is two things, and both are generic:

    pattern       which calls it answers to
    extract_args  what such a call carries, as a dictionary

The dictionary is the shape's whole meaning, and it is why shapes live here
rather than in a backend: `( R )+` carries a body and a marker whoever is
generating from it, so every backend reads the same names. What a call then
*produces* is the backend's business, and belongs to a `MacroDefinition`.

A grammar's own `d` definition is a shape too — `definition_shape` builds it —
whose pattern matches its signature exactly and whose dictionary binds each
argument to the parameter it fills.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from ..lexing.cst import Item, arguments_of

#: Reads a matched call: the item, and the match of its shape's pattern. The
#: keys of the result are the parameter names a `produce_call` is written with.
ExtractArgs = Callable[[Item, re.Match[str]], dict[str, object]]


@dataclass(frozen=True, slots=True)
class MacroShape:
    """A name-pattern, and what a call of it carries."""

    name: str  # what the shape is called, in messages and dumps
    pattern: re.Pattern[str]
    extract_args: ExtractArgs

    def match(self, signature: str) -> re.Match[str] | None:
        """Whether a signature calls this shape, and what its pattern captured."""
        return self.pattern.fullmatch(signature)


def shape(name: str, pattern: str, extract_args: ExtractArgs) -> MacroShape:
    """Define a shape, compiling its pattern.

    The pattern is matched against a whole signature, so it needs no anchors.
    """
    return MacroShape(name=name, pattern=re.compile(pattern), extract_args=extract_args)


# -- the pieces a signature is written from --------------------------------

#: One character of a name: escaped, or a plain character that is no bracket.
#: A signature escapes its brackets, so an unescaped one is always a group.
NAME_CHARACTER = r"(?:\\.|[^\\()])"

#: A name carrying no groups, e.g. `Digit`, and one carrying at least one, e.g.
#: `sep()by()`. Between them they cover every item that is a plain call.
NAME_PATTERN = rf"{NAME_CHARACTER}*"
ARGUMENTS_PATTERN = rf"{NAME_PATTERN}(?:\(\){NAME_PATTERN})+"


# -- the built-in shapes ---------------------------------------------------


def _subgroup_args(item: Item, match: re.Match[str]) -> dict[str, object]:
    return {"body": item.groups[0]}


def _repetition_args(item: Item, match: re.Match[str]) -> dict[str, object]:
    return {"body": item.groups[0], "marker": match["marker"]}


def _choice_args(item: Item, match: re.Match[str]) -> dict[str, object]:
    return {"options": item.groups, "symbol": match["symbol"]}


def _no_args(item: Item, match: re.Match[str]) -> dict[str, object]:
    return {}


SUBGROUP = shape("subgroup", r"\(\)", _subgroup_args)
REPETITION = shape("repetition", r"\(\)(?P<marker>[+*?])", _repetition_args)
#: The separators must all be the same one, which is what the backreference says.
CHOICE = shape("choice", r"\(\)(?P<symbol>[|/])\(\)(?:(?P=symbol)\(\))*", _choice_args)

#: The two shapes a `d` definition is looked up by. They match any name, and the
#: definition found under it carries the shape that reads the call's arguments.
NAME = shape("name", NAME_PATTERN, _no_args)
NAME_WITH_ARGUMENTS = shape("name-with-arguments", ARGUMENTS_PATTERN, _no_args)


# -- the shape of a grammar's own definition -------------------------------


def definition_shape(signature: str, parameters: list[str]) -> MacroShape:
    """The shape a `d Head = Body` line answers to.

    The pattern is the head's signature, matched exactly, and the dictionary
    binds each slot's argument to the parameter it fills, so a definition
    written `d sep(R)by(S)` is called with `R` and `S`.
    """

    def extract_args(item: Item, match: re.Match[str]) -> dict[str, object]:
        return dict(zip(parameters, arguments_of(item)))

    return MacroShape(
        name=signature,
        pattern=re.compile(re.escape(signature)),
        extract_args=extract_args,
    )
