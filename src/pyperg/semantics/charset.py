"""Character sets (Part 3): `a`, `0-9`, `a-z|A-Z|_`, `Lu|Decimal_Number`.

Not implemented yet.

A set is bare text of one or more parts separated by `|`. A part is a single
character, a range `E-F` of two single characters, or the name of a Unicode
category, given as a two-letter abbreviation (`Lu`, `Nd`) or in long form
(`Uppercase_Letter`). The one-letter abbreviations are unavailable, since a
single character is already a character part.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class CharacterPart:
    """One part of a set: a character, a range, or a category."""

    kind: str  # "character", "range" or "category"
    value: str  # the character, the category name, or the low end of a range
    high: str = ""  # the high end of a range


@dataclass(slots=True)
class CharacterSet:
    """The union of one or more parts."""

    parts: list[CharacterPart]

    def matches(self, char: str) -> bool:
        """Whether a character belongs to the union."""
        raise NotImplementedError


def parse_character_set(text: str) -> CharacterSet | None:
    """Read bare text as a character set, or return None if it is no such shape.

    Splitting on `|` is safe: no category name contains `-` or `|`, and none is a
    single character, so the three part shapes never overlap.
    """
    raise NotImplementedError


def is_category_name(text: str) -> bool:
    """Whether the text names a recognised Unicode category."""
    raise NotImplementedError
