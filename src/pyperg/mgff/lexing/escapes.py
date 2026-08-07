"""MGFF escapes (specification Part 1).

An escape denotes exactly one character, and the set is closed: a backslash
followed by anything not listed here is an error. The character an escape
produces is ordinary text and carries no special role, so `\\x28` is the text
`(` and never opens a group.

Errors are raised without a span; the lexer knows the offsets and re-raises.
"""

from __future__ import annotations

import unicodedata

from ...diagnostics.errors import LexError

# Single-character escapes. `\_` (space) is particular to MGFF.
SIMPLE_ESCAPES: dict[str, str] = {
    "(": "(",
    ")": ")",
    "\\": "\\",
    "_": " ",
    "0": "\0",
    "a": "\a",
    "b": "\b",
    "f": "\f",
    "n": "\n",
    "r": "\r",
    "t": "\t",
    "v": "\v",
}

# Numeric escapes: introducer -> exact count of hexadecimal digits.
NUMERIC_ESCAPES: dict[str, int] = {"x": 2, "u": 4, "U": 8}

_HEX_DIGITS = set("0123456789abcdefABCDEF")

# Characters allowed in a `\<NAME>` Unicode character name.
_NAME_CHARS = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_")


def _code_point(value: int) -> str:
    """Turn a numeric escape's value into a character, rejecting the invalid range."""
    if value > 0x10FFFF:
        raise LexError(
            f"escape denotes U+{value:X}, above the maximum code point U+10FFFF"
        )
    if 0xD800 <= value <= 0xDFFF:
        raise LexError(f"escape denotes the surrogate code point U+{value:04X}")
    return chr(value)


def read_escape(text: str, index: int) -> tuple[str, int]:
    """Read the escape starting at `text[index]` (a backslash).

    Returns the character it denotes and the index just past the escape.
    Raises `LexError` if the escape is unknown, truncated or out of range.
    """
    assert text[index] == "\\"
    if index + 1 >= len(text):
        raise LexError("backslash at end of input")

    kind = text[index + 1]

    # Whitespace is written `\_` or `\t`, never as an escaped literal space.
    if kind in " \t":
        raise LexError("backslash followed by whitespace; write \\_ or \\t")
    if kind in "\r\n":
        raise LexError("backslash at end of line")

    if kind in SIMPLE_ESCAPES:
        return SIMPLE_ESCAPES[kind], index + 2

    # \xhh, \uhhhh, \UHHHHHHHH: an exact count of hexadecimal digits.
    if kind in NUMERIC_ESCAPES:
        count = NUMERIC_ESCAPES[kind]
        digits = text[index + 2 : index + 2 + count]
        if len(digits) < count or any(d not in _HEX_DIGITS for d in digits):
            raise LexError(f"\\{kind} needs exactly {count} hexadecimal digits")
        return _code_point(int(digits, 16)), index + 2 + count

    # \<NAME>: a Unicode character name, upper case with _ for each space.
    if kind == "<":
        end = text.find(">", index + 2)
        if end < 0:
            raise LexError("unterminated \\<NAME> escape")
        name = text[index + 2 : end]
        if not name or any(c not in _NAME_CHARS for c in name):
            raise LexError(f"invalid character name {name!r}")
        try:
            found = unicodedata.lookup(name.replace("_", " "))
        except KeyError:
            raise LexError(f"no character is named {name!r}") from None
        # `lookup` answers named *sequences* as well — `KEYCAP_NUMBER_SIGN` is
        # three code points — and an escape denotes exactly one character. Such
        # a name is rejected here, where what is wrong can still be said; read
        # on, it would reach the resolver as an unknown name spelled in
        # characters nobody wrote.
        if len(found) != 1:
            raise LexError(
                f"{name!r} names a sequence of {len(found)} characters, and an "
                "escape denotes exactly one; write them out one escape each"
            )
        return found, end + 1

    raise LexError(f"unknown escape \\{kind}")


def escape_char(char: str) -> str:
    """Render a character back into MGFF text, escaping it where required."""
    for form, produced in SIMPLE_ESCAPES.items():
        if char == produced:
            return "\\" + form
    if char.isprintable():
        return char
    return f"\\u{ord(char):04X}" if ord(char) <= 0xFFFF else f"\\U{ord(char):08X}"
