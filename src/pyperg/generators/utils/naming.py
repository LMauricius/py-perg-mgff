"""Names for generated symbols.

A grammar names its macros freely — a macro may be called `+` — while most
output languages want identifiers. These helpers turn one into the other and
keep the result unique.
"""

from __future__ import annotations

import re

#: Characters an identifier may hold after the first.
_UNSAFE = re.compile(r"[^0-9A-Za-z_]")

#: What each punctuation character is spelled as when a name is made safe.
PUNCTUATION_NAMES: dict[str, str] = {
    "+": "Plus",
    "-": "Minus",
    "*": "Star",
    "/": "Slash",
    "\\": "Backslash",
    "=": "Equals",
    "<": "Less",
    ">": "Greater",
    "(": "LParen",
    ")": "RParen",
    "[": "LBracket",
    "]": "RBracket",
    "{": "LBrace",
    "}": "RBrace",
    ",": "Comma",
    ".": "Dot",
    ":": "Colon",
    ";": "Semicolon",
    "!": "Bang",
    "?": "Question",
    "&": "Amp",
    "|": "Pipe",
    "^": "Caret",
    "%": "Percent",
    "#": "Hash",
    "@": "At",
    "$": "Dollar",
    "~": "Tilde",
    "'": "Quote",
    '"': "DoubleQuote",
    "`": "Backtick",
    " ": "Space",
}


def safe_identifier(name: str, fallback: str = "Rule") -> str:
    """A name an output language will accept as an identifier.

    Punctuation is spelled out where it has a name and dropped to `_` otherwise,
    and a name that would start with a digit is prefixed.
    """
    spelled = "".join(PUNCTUATION_NAMES.get(char, char) for char in name)
    cleaned = _UNSAFE.sub("_", spelled).strip("_")
    if not cleaned:
        return fallback
    return cleaned if not cleaned[0].isdigit() else f"{fallback}_{cleaned}"


def pascal_case(name: str) -> str:
    """`assign_list` and `assign-list` both give `AssignList`."""
    words = [word for word in re.split(r"[^0-9A-Za-z]+", name) if word]
    return "".join(word[:1].upper() + word[1:] for word in words)


def snake_case(name: str) -> str:
    """`AssignList` gives `assign_list`."""
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", name)
    words = [word for word in re.split(r"[^0-9A-Za-z]+", spaced) if word]
    return "_".join(word.lower() for word in words)


class NameAllocator:
    """Hands out names, appending a number to keep each one unique."""

    def __init__(self, reserved: set[str] | None = None) -> None:
        self.taken: set[str] = set(reserved or ())
        #: The name each key was given, so asking twice gives the same answer.
        self.assigned: dict[str, str] = {}

    def allocate(self, wanted: str, key: str | None = None) -> str:
        """Claim a name, or return the one already given to this key."""
        if key is not None and key in self.assigned:
            return self.assigned[key]
        name = wanted
        counter = 2
        while name in self.taken:
            name = f"{wanted}{counter}"
            counter += 1
        self.taken.add(name)
        if key is not None:
            self.assigned[key] = name
        return name
