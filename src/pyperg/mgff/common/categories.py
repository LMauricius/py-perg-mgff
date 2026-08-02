"""The Unicode categories a character set may name.

A category is given as a two-letter abbreviation (`Lu`, `Nd`) or in long form
(`Uppercase_Letter`). The one-letter abbreviations are unavailable, since a
single character is already a character part; the long form of a group —
`Letter`, `Number` — names the whole of it instead.

This is the one place the recognised categories are written down. Everything
else, the backends included, reads them from here rather than keeping tables of
its own.
"""

from __future__ import annotations

#: Keyed by the canonical abbreviation. `LC` and the one-letter group names are
#: not real `unicodedata.category` results; `CATEGORY_GROUPS` records which
#: concrete categories each of them stands for.
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
    # spellings accepted below; only these long forms name a whole group.
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

#: Every accepted spelling -> the canonical abbreviation. A two-letter
#: abbreviation names itself; a long form names its abbreviation. One-letter
#: spellings are left out, since a single character is a character part.
CATEGORY_NAMES: dict[str, str] = {
    **{
        abbreviation: abbreviation
        for abbreviation in CATEGORY_LONG_NAMES
        if len(abbreviation) > 1
    },
    **{long: abbreviation for abbreviation, long in CATEGORY_LONG_NAMES.items()},
}


def category_members(abbreviation: str) -> tuple[str, ...]:
    """The concrete `unicodedata` categories a canonical abbreviation covers."""
    return CATEGORY_GROUPS.get(abbreviation, (abbreviation,))


def is_category_name(text: str) -> bool:
    """Whether the text names a recognised Unicode category."""
    return text in CATEGORY_NAMES
