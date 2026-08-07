"""Character sets (Part 3): `a`, `0-9`, `a-z|A-Z|_`, `Lu|Decimal_Number`.

A set is bare text of one or more parts separated by `|`. A part is a single
character, a range `E-F` of two single characters, or the name of a Unicode
category — the recognised ones are listed in `categories`.

The separator is an ordinary character too, and there is no escape for it: `\\|`
is not an escape sequence, so the text reaching this module cannot say which
role a `|` plays. What settles it is that **no part is empty**. A `|` that a
part cannot be read from is the separator, and one that would otherwise leave an
empty part beside it is a character: `a||` is `a` and `|`, `|` alone is `|`, and
`|-~` is the range from `|` to `~`. Reading therefore backtracks rather than
splits.

What a set *is* lives here: the two classes, and the reading of text into them.
Nothing in this module knows about shapes, macros or rule trees, so it can be
read on its own. The shapes that recognise a set in a grammar are in
`characters`.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Iterator
from dataclasses import dataclass

from .categories import CATEGORY_NAMES, categories_covered_by

SEPARATOR = "|"
RANGE_SEPARATOR = "-"


@dataclass(slots=True)
class CharacterSetPart:
    """One part of a set: a character, a range, or a category."""

    kind: str  # "character", "range" or "category"
    value: str  # the character, the category name, or the low end of a range
    high: str = ""  # the high end of a range

    def matches(self, char: str) -> bool:
        """Whether a single character belongs to this part."""
        if self.kind == "character":
            return char == self.value
        if self.kind == "range":
            return self.value <= char <= self.high
        return unicodedata.category(char) in categories_covered_by(self.value)


@dataclass(slots=True)
class CharacterSet:
    """The union of one or more parts."""

    parts: list[CharacterSetPart]

    def matches(self, char: str) -> bool:
        """Whether a character belongs to the union."""
        return any(part.matches(char) for part in self.parts)

    @property
    def single_character(self) -> str | None:
        """The one character the set accepts, or None if it accepts more."""
        if len(self.parts) == 1 and self.parts[0].kind == "character":
            return self.parts[0].value
        return None


# -- reading text into a set -----------------------------------------------

#: Category names longest first, so `Lu` cannot win over a longer name starting
#: with it. Categories are tried whole; none is a single character and none
#: holds `-` or `|`, so the three part shapes never overlap.
_CATEGORY_NAMES_LONGEST_FIRST = sorted(CATEGORY_NAMES, key=len, reverse=True)


def _parts_beginning_at(
    text: str, index: int
) -> Iterator[tuple[CharacterSetPart, int]]:
    """Every part the text can begin with at `index`, each with the index past it.

    Longer readings come first, so a range or a category is preferred over the
    single character starting it. A `|` is offered as a character like any
    other; whether it is one is decided by whether the rest reads.
    """
    if index >= len(text):
        return
    # A range needs single characters on both sides: three characters with the
    # range separator in the middle. `9-0` is no range and is not offered.
    if index + 2 < len(text) and text[index + 1] == RANGE_SEPARATOR:
        low, high = text[index], text[index + 2]
        if low <= high:
            yield CharacterSetPart("range", low, high), index + 3
    for name in _CATEGORY_NAMES_LONGEST_FIRST:
        if text.startswith(name, index):
            yield CharacterSetPart("category", CATEGORY_NAMES[name]), index + len(name)
    yield CharacterSetPart("character", text[index]), index + 1


def _parts_from(
    text: str, index: int, memo: dict[int, list[CharacterSetPart] | None]
) -> list[CharacterSetPart] | None:
    """The parts the text spells from `index` on, or None if it spells none.

    Each candidate part must be followed by the end of the text or by a
    separator and at least one further part — that is the no-empty-part rule,
    and the whole of what tells a separator from a `|` that is a part itself.
    `memo` keeps what each index answered: the reading of a tail depends on the
    tail alone, so backtracking never re-reads one.
    """
    if index in memo:
        return memo[index]
    memo[index] = None  # No cycle is possible: every part consumes a character.
    for part, next_index in _parts_beginning_at(text, index):
        if next_index == len(text):
            rest: list[CharacterSetPart] | None = []
        elif text[next_index] == SEPARATOR:
            rest = _parts_from(text, next_index + 1, memo)
        else:
            continue  # The part stopped mid-text with no separator to follow.
        if rest is None:
            continue
        memo[index] = [part, *rest]
        return memo[index]
    return None


def parse_character_set_part(text: str) -> CharacterSetPart | None:
    """Read the whole text as one part, or return None if it is no valid part."""
    for part, next_index in _parts_beginning_at(text, 0):
        if next_index == len(text):
            return part
    return None


def parse_character_set(text: str) -> CharacterSet | None:
    """Read bare text as a character set, or return None if it is no such shape."""
    parts = _parts_from(text, 0, {})
    return CharacterSet(parts) if parts else None
