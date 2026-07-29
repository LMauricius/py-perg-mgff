"""Interpretation of an item by its shape (Part 2, extended by Part 3).

Not implemented yet.

Each item is read by the first rule that matches, highest rank first:

    subgroup       `( … )` alone
    repetition     `( R )+`, `( R )*`, `( R )?`
    choice         `(O1)|(O2)|…`, `(O1)/(O2)/…`, no whitespace around the separator
    call           any item carrying arguments, e.g. `sep(x)by(y)`
    character set  bare text of two or more parts, e.g. `a-z|A-Z|_`
    call           an argument-less call, e.g. `Digit`
    character set  bare text of a single part, e.g. `a`, `0-9`, `Lu`

The two character-set ranks are why a production may still be named `x` or
`Letter` and be called by that name.
"""

from __future__ import annotations

from enum import Enum

from ..mgff.cst import Item


class Shape(Enum):
    """What an item is read as."""

    SUBGROUP = "subgroup"
    REPETITION = "repetition"
    CHOICE = "choice"
    CALL_WITH_ARGUMENTS = "call-with-arguments"
    CHARACTER_SET = "character-set"
    CALL = "call"


def classify(item: Item, character_sets_allowed: bool) -> Shape:
    """Read an item's shape.

    `character_sets_allowed` is set by the target: only targets matching textual
    characters, such as `Lex`, add the character-set shapes.
    """
    # 1. A lone group is a subgroup.
    # 2. A single group with a trailing +, * or ? is a repetition.
    # 3. Alternating groups and bare / or | separators are a choice.
    # 4. Any remaining item with groups is a call carrying arguments.
    # 5. Bare text: a character set of several parts, else a call, else a
    #    single-part character set.
    raise NotImplementedError


def is_choice(item: Item) -> bool:
    """True for `(O1)|(O2)|…` or `(O1)/(O2)/…`, all separators the same."""
    raise NotImplementedError


def is_repetition(item: Item) -> tuple[bool, str]:
    """True and the marker for `( R )+`, `( R )*` and `( R )?`."""
    raise NotImplementedError
