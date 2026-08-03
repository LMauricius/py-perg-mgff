"""How a signature is spelled, and the shapes matched against one directly.

A signature is an item's text with every group replaced by an empty pair of
parentheses. The patterns below are written from that alphabet, so a shape can
say "any name" or "any name carrying arguments" without knowing what names a
particular grammar defines.

`definition_shape` is the one shape built here: the shape a `d Head = Body`
line answers to. Its pattern is the head's signature matched exactly, and its
dictionary binds each argument to the parameter it fills.

The alphabet and the `shape` builder are shared. `mgff.common` writes its own
shapes from them — `( R )+`, a character set, and the two "any name at all"
filters a `Scoped` entry consults a scope through.
"""

from __future__ import annotations

import re

from ..lexing.cst import Item, arguments_of
from .shapes import ExtractArgs, MacroShape


def shape(name: str, pattern: str, extract_args: ExtractArgs) -> MacroShape:
    """Define a shape, compiling its pattern.

    The pattern is matched against a whole signature, so it needs no anchors.
    """
    return MacroShape(name=name, pattern=re.compile(pattern), extract_args=extract_args)


def no_args(item: Item, match: re.Match[str]) -> dict[str, object]:
    """The extractor of a shape whose calls carry nothing."""
    return {}


# -- the pieces a signature is written from --------------------------------

#: One character of a name: escaped, or a plain character that is no bracket.
#: A signature escapes its brackets, so an unescaped one is always a group.
NAME_CHARACTER = r"(?:\\.|[^\\()])"

#: A name carrying no groups, e.g. `Digit`, and one carrying at least one, e.g.
#: `sep()by()`. Between them they cover every item that is a plain call.
NAME_PATTERN = rf"{NAME_CHARACTER}*"
ARGUMENTS_PATTERN = rf"{NAME_PATTERN}(?:\(\){NAME_PATTERN})+"


# -- the shape of a grammar's own definition -------------------------------


def signature_to_shape(signature: str, parameters: list[str]) -> MacroShape:
    """The shape a `d Head = Body` line answers to.

    The pattern is the head's signature, matched exactly, and the dictionary
    binds each slot's argument to the parameter it fills, so a definition
    written `d sep(R)by(S)` is called with `R` and `S`.

    The arguments come from the item alone, and `match` is deliberately unused: a
    definition is selected by looking its name up, not by matching this pattern,
    and the two need not even agree. A prefix scope files `pair` under
    `Util_pair`, so the match handed over is the one from the `Scoped` filter
    that found it.
    """

    def extract_args(item: Item, match: re.Match[str]) -> dict[str, object]:
        return dict(zip(parameters, arguments_of(item)))

    return MacroShape(
        name=signature,
        pattern=re.compile(re.escape(signature)),
        extract_args=extract_args,
    )
