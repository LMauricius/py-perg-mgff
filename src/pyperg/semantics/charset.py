"""Character sets (Part 3): `a`, `0-9`, `a-z|A-Z|_`, `Lu|Decimal_Number`.

A set is bare text of one or more parts separated by `|`. A part is a single
character, a range `E-F` of two single characters, or the name of a Unicode
category, given as a two-letter abbreviation (`Lu`, `Nd`) or in long form
(`Uppercase_Letter`). The one-letter abbreviations are unavailable, since a
single character is already a character part.

Character sets reach the resolver as two macros, `CHARACTER_SET` for a set of
several parts and `CHARACTER` for one of a single part. They have the same body
and differ only in where they sit in the order, which is the whole of why
`a-z|A-Z` is a set even where a production bears that name while a lone `Letter`
is not.

The category table below is the one place the recognised categories are named;
the backends import it from here rather than keeping tables of their own.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from ..grammar.macros import MacroDefinition
from ..grammar.shapes import MacroShape, shape
from ..mgff.cst import Item
from .nodes import MacroCall, Node

# -- the recognised Unicode categories ------------------------------------
#
# Keyed by the canonical abbreviation. `LC` and the one-letter group names are
# not real `unicodedata.category` results, so `CATEGORY_GROUPS` records which
# concrete categories each of them stands for.

CATEGORY_LONG_NAMES: dict[str, str] = {
    "Lu": "Uppercase_Letter",
    "Ll": "Lowercase_Letter",
    "Lt": "Titlecase_Letter",
    "Lm": "Modifier_Letter",
    "Lo": "Other_Letter",
    "Mn": "Nonspacing_Mark",
    "Mc": "Spacing_Mark",
    "Me": "Enclosing_Mark",
    "Nd": "Decimal_Number",
    "Nl": "Letter_Number",
    "No": "Other_Number",
    "Pc": "Connector_Punctuation",
    "Pd": "Dash_Punctuation",
    "Ps": "Open_Punctuation",
    "Pe": "Close_Punctuation",
    "Pi": "Initial_Punctuation",
    "Pf": "Final_Punctuation",
    "Po": "Other_Punctuation",
    "Sm": "Math_Symbol",
    "Sc": "Currency_Symbol",
    "Sk": "Modifier_Symbol",
    "So": "Other_Symbol",
    "Zs": "Space_Separator",
    "Zl": "Line_Separator",
    "Zp": "Paragraph_Separator",
    "Cc": "Control",
    "Cf": "Format",
    "Cs": "Surrogate",
    "Co": "Private_Use",
    "Cn": "Unassigned",
    # Groups. The one-letter abbreviations are deliberately absent from the
    # spelling accepted below; only these long forms name a whole group.
    "L": "Letter",
    "LC": "Cased_Letter",
    "M": "Mark",
    "N": "Number",
    "P": "Punctuation",
    "S": "Symbol",
    "Z": "Separator",
    "C": "Other",
}

CATEGORY_GROUPS: dict[str, tuple[str, ...]] = {
    "L": ("Lu", "Ll", "Lt", "Lm", "Lo"),
    "LC": ("Lu", "Ll", "Lt"),
    "M": ("Mn", "Mc", "Me"),
    "N": ("Nd", "Nl", "No"),
    "P": ("Pc", "Pd", "Ps", "Pe", "Pi", "Pf", "Po"),
    "S": ("Sm", "Sc", "Sk", "So"),
    "Z": ("Zs", "Zl", "Zp"),
    "C": ("Cc", "Cf", "Cs", "Co", "Cn"),
}

# Every accepted spelling -> the canonical abbreviation. A two-letter
# abbreviation names itself; a long form names its abbreviation. One-letter
# spellings are left out, since a single character is a character part.
CATEGORY_NAMES: dict[str, str] = {
    **{
        abbreviation: abbreviation
        for abbreviation in CATEGORY_LONG_NAMES
        if len(abbreviation) > 1
    },
    **{long: abbreviation for abbreviation, long in CATEGORY_LONG_NAMES.items()},
}

SEPARATOR = "|"
RANGE_SEPARATOR = "-"


@dataclass(slots=True)
class CharacterPart:
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
        return unicodedata.category(char) in category_members(self.value)


@dataclass(slots=True)
class CharacterSet:
    """The union of one or more parts."""

    parts: list[CharacterPart]

    def matches(self, char: str) -> bool:
        """Whether a character belongs to the union."""
        return any(part.matches(char) for part in self.parts)

    @property
    def single_character(self) -> str | None:
        """The one character the set accepts, or None if it accepts more."""
        if len(self.parts) == 1 and self.parts[0].kind == "character":
            return self.parts[0].value
        return None


def category_members(abbreviation: str) -> tuple[str, ...]:
    """The concrete `unicodedata` categories a canonical abbreviation covers."""
    return CATEGORY_GROUPS.get(abbreviation, (abbreviation,))


def is_category_name(text: str) -> bool:
    """Whether the text names a recognised Unicode category."""
    return text in CATEGORY_NAMES


def parse_part(text: str) -> CharacterPart | None:
    """Read one part of a set, or return None if the text is no valid part."""
    if len(text) == 1:
        return CharacterPart("character", text)
    # A range needs single characters on both sides, so it is exactly three
    # characters long with the separator in the middle.
    if len(text) == 3 and text[1] == RANGE_SEPARATOR:
        low, high = text[0], text[2]
        return CharacterPart("range", low, high) if low <= high else None
    if text in CATEGORY_NAMES:
        return CharacterPart("category", CATEGORY_NAMES[text])
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
        return CharacterSet([CharacterPart("character", SEPARATOR)])
    parts: list[CharacterPart] = []
    for piece in text.split(SEPARATOR):
        part = parse_part(piece)
        if part is None:
            return None
        parts.append(part)
    return CharacterSet(parts)


# -- the macros ------------------------------------------------------------

#: One character as a signature spells it: escaped, or a plain character that is
#: neither a bracket nor the separator. Brackets are always escaped in a
#: signature, so an unescaped one can only be a group.
_CHARACTER = r"(?:\\.|[^\\()|])"

#: A category, longest name first, so `Lu` cannot win over `Lu…` — the names
#: come from the table above, which is the only place they are written down.
_CATEGORY = "|".join(
    re.escape(name) for name in sorted(CATEGORY_NAMES, key=len, reverse=True)
)

#: One part: a range, a category, or a single character, tried in that order.
_PART = rf"(?:{_CHARACTER}-{_CHARACTER}|{_CATEGORY}|{_CHARACTER})"

#: A set of two or more parts, and a set of exactly one. The lone separator is
#: the separator character itself rather than an empty set, so it is spelled out.
CHARACTER_SET_PATTERN = rf"{_PART}(?:\|{_PART})+"
CHARACTER_PATTERN = rf"(?:{_PART}|\|)"


def _set_args(item: Item, match: re.Match[str]) -> dict[str, object]:
    """What a character set carries: the text that spells it."""
    return {"item": item, "text": item.text}


def _character_set(item: Item, text: str) -> Node | None:
    """A character set as a node, declining when the text is no valid set.

    The pattern is a shape and cannot compare the ends of a range, so `9-0`
    reaches this point and is declined here. It goes on to be read as a name, and
    is reported as an unknown one.
    """
    if parse_character_set(text) is None:
        return None
    return MacroCall(macro=CHARACTER_SET, item=item)


#: A set of several parts outranks a production of the same name; a set of one
#: part yields to it. That is the whole difference between the two.
SET_SHAPE: MacroShape = shape("character-set", CHARACTER_SET_PATTERN, _set_args)
CHARACTER_SHAPE: MacroShape = shape("character", CHARACTER_PATTERN, _set_args)

CHARACTER_SET = MacroDefinition(shape=SET_SHAPE, produce_call=_character_set)
CHARACTER = MacroDefinition(shape=CHARACTER_SHAPE, produce_call=_character_set)


def character_set_of(node: Node) -> CharacterSet | None:
    """The set a node matches one character from, or None for any other node."""
    # Both macros build the same node, so one identity answers for either.
    if isinstance(node, MacroCall) and node.macro is CHARACTER_SET:
        return parse_character_set(node.item.text)
    return None
