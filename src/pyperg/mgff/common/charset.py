"""Character sets (Part 3): `a`, `0-9`, `a-z|A-Z|_`, `Lu|Decimal_Number`.

A set is bare text of one or more parts separated by `|`. A part is a single
character, a range `E-F` of two single characters, or the name of a Unicode
category — the recognised ones are listed in `categories`.

What a set *is* lives here: the two classes, and the reading of text into them.
Nothing in this module knows about shapes, macros or rule trees, so it can be
read on its own. The shapes that recognise a set in a grammar are in
`characters`.
"""

from __future__ import annotations

import unicodedata
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


def parse_character_set_part(text: str) -> CharacterSetPart | None:
    """Read one part of a set, or return None if the text is no valid part."""
    if len(text) == 1:
        return CharacterSetPart("character", text)
    # A range needs single characters on both sides, so it is exactly three
    # characters long with the separator in the middle.
    if len(text) == 3 and text[1] == RANGE_SEPARATOR:
        low, high = text[0], text[2]
        return CharacterSetPart("range", low, high) if low <= high else None
    if text in CATEGORY_NAMES:
        return CharacterSetPart("category", CATEGORY_NAMES[text])
    return None


def parse_character_set(text: str) -> CharacterSet | None:
    """Read bare text as a character set, or return None if it is no such shape.

    Splitting on `|` is safe: no category name contains `-` or `|`, and none is a
    single character, so the three part shapes never overlap.
    """
    if not text:
        return None
    # A lone `|` is the separator character itself, not an empty set.
    if text == SEPARATOR:
        return CharacterSet([CharacterSetPart("character", SEPARATOR)])
    parts: list[CharacterSetPart] = []
    for piece in text.split(SEPARATOR):
        part = parse_character_set_part(piece)
        if part is None:
            return None
        parts.append(part)
    return CharacterSet(parts)
