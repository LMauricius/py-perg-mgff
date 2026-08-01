"""Interpretation of an item by its shape (Part 2, extended by Part 3).

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

Only the last rank needs to know whether a name resolves, so `classify` takes an
optional `resolves` predicate. Without it a single-part set is reported as a
call, which is what the caller wants while it is still building symbol tables.
"""

from __future__ import annotations

from collections.abc import Callable
from enum import Enum

from ..mgff.cst import Group, Item, Text
from .builtins import CHOICE_MARKERS, REPETITION_MARKERS
from .charset import parse_character_set


class Shape(Enum):
    """What an item is read as."""

    SUBGROUP = "subgroup"
    REPETITION = "repetition"
    CHOICE = "choice"
    CALL_WITH_ARGUMENTS = "call-with-arguments"
    CHARACTER_SET = "character-set"
    CALL = "call"


def classify(
    item: Item,
    character_sets_allowed: bool,
    resolves: Callable[[str], bool] | None = None,
) -> Shape:
    """Read an item's shape.

    `character_sets_allowed` is set by the target: only targets matching textual
    characters, such as `Lex`, add the character-set shapes. `resolves` answers
    whether a bare name is a visible macro, which decides the last rank alone.
    """
    # 1. A lone group is a subgroup.
    if item.is_bare_group:
        return Shape.SUBGROUP

    # 2. A single group with a trailing +, * or ? is a repetition.
    repeats, _ = is_repetition(item)
    if repeats:
        return Shape.REPETITION

    # 3. Alternating groups and bare / or | separators are a choice.
    if is_choice(item):
        return Shape.CHOICE

    # 4. Any remaining item with groups is a call carrying arguments.
    if not item.is_bare_text:
        return Shape.CALL_WITH_ARGUMENTS

    # 5. Bare text: a character set of several parts, else a call, else a
    #    single-part character set.
    if not character_sets_allowed:
        return Shape.CALL
    characters = parse_character_set(item.text)
    if characters is None:
        return Shape.CALL
    if len(characters.parts) > 1:
        return Shape.CHARACTER_SET
    # A single part yields to a production of the same name; without a
    # predicate the caller cannot know yet, so it hears the higher rank.
    if resolves is None:
        return Shape.CALL
    return Shape.CALL if resolves(item.text) else Shape.CHARACTER_SET


def is_choice(item: Item) -> bool:
    """True for `(O1)|(O2)|…` or `(O1)/(O2)/…`, all separators the same."""
    return choice_symbol(item) is not None


def choice_symbol(item: Item) -> str | None:
    """The separator of a choice item, or None when the item is no choice.

    The parts must alternate group, separator, group, starting and ending with a
    group, and every separator must be the same single marker character.
    """
    parts = item.parts
    if len(parts) < 3 or len(parts) % 2 == 0:
        return None
    symbol: str | None = None
    for index, part in enumerate(parts):
        if index % 2 == 0:
            if not isinstance(part, Group):
                return None
        else:
            if not isinstance(part, Text) or part.value not in CHOICE_MARKERS:
                return None
            if symbol is not None and part.value != symbol:
                return None
            symbol = part.value
    return symbol


def is_repetition(item: Item) -> tuple[bool, str]:
    """True and the marker for `( R )+`, `( R )*` and `( R )?`."""
    parts = item.parts
    if len(parts) != 2 or not isinstance(parts[0], Group):
        return False, ""
    marker = parts[1]
    if not isinstance(marker, Text) or marker.value not in REPETITION_MARKERS:
        return False, ""
    return True, marker.value


def group_items(group: Group) -> list[Item]:
    """Every item of a group, its lines joined into one sequence.

    The line breaks inside a group are a matter of layout, so a subgroup and a
    choice option both read their contents this way.
    """
    return [item for line in group.lines for item in line.items]
