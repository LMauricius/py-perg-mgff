"""Characters and character sets in ANTLR's own notation.

ANTLR spells characters twice over, and the two spellings do not agree. A fixed
string is a **literal** in single quotes, legal in a lexer rule and in a parser
rule alike; a set of characters is written `[ … ]` and is legal in a lexer rule
only, since a parser reads tokens and has no character to match.

The escapes are ANTLR's, not PCRE's, which is why none of this reuses
`utils.regex`: ANTLR knows `\\n \\r \\t \\f \\b`, `\\uXXXX` and the extended
`\\u{XXXXXX}`, and nothing else. It has no `\\v`, and an escape it does not know
is an error rather than the character itself, so anything unusual is written as a
code point instead of being passed through.

A set is a union of positive parts, which is exactly what MGFF's character set is
— neither notation has a negation — so the two map across part for part.
"""

from __future__ import annotations

from ...mgff.common.charset import CharacterSet, CharacterSetPart

#: The escapes ANTLR spells with a letter. `\v` is deliberately absent: ANTLR
#: has no such escape, so a vertical tab goes out as its code point.
_CONTROL_ESCAPES = {"\n": "\\n", "\r": "\\r", "\t": "\\t", "\f": "\\f", "\b": "\\b"}

#: Characters that need a backslash inside `' … '`.
_LITERAL_METACHARACTERS = frozenset("'\\")

#: Characters that need a backslash inside `[ … ]`.
_SET_METACHARACTERS = frozenset("]\\-")


def _code_point_escape(char: str) -> str:
    """One character as `\\uXXXX`, or as `\\u{XXXXX}` above the basic plane."""
    code = ord(char)
    if code > 0xFFFF:
        return f"\\u{{{code:X}}}"
    return f"\\u{code:04X}"


def _escaped(char: str, metacharacters: frozenset[str]) -> str:
    """One character, escaped for whichever of the two contexts asks.

    A character better not written raw — a control character, and the two
    non-characters at the end of the basic plane — goes out as a code point,
    since it survives no round trip through a text editor.
    """
    if char in metacharacters:
        return "\\" + char
    if char in _CONTROL_ESCAPES:
        return _CONTROL_ESCAPES[char]
    if ord(char) < 0x20 or ord(char) == 0x7F or ord(char) in (0xFFFE, 0xFFFF):
        return _code_point_escape(char)
    return char


def escape_in_literal(char: str) -> str:
    """One character as it appears inside `' … '`."""
    return _escaped(char, _LITERAL_METACHARACTERS)


def escape_in_set(char: str) -> str:
    """One character as it appears inside `[ … ]`."""
    return _escaped(char, _SET_METACHARACTERS)


def antlr_literal(text: str) -> str:
    """A fixed string as the literal that matches it: `<=` gives `'<='`."""
    return "'" + "".join(escape_in_literal(char) for char in text) + "'"


def character_set_part(part: CharacterSetPart) -> str:
    """One part of a set, as it appears inside `[ … ]`."""
    if part.kind == "character":
        return escape_in_set(part.value)
    if part.kind == "range":
        return f"{escape_in_set(part.value)}-{escape_in_set(part.high)}"
    return f"\\p{{{part.value}}}"


def antlr_character_set(characters: CharacterSet) -> str:
    """A set as the lexer element matching one character from it.

    A single character is written as a literal, which reads better and is the one
    form a parser rule accepts too. Everything else needs the brackets — a lone
    category among it, since `\\p{ … }` is only legal inside a set.
    """
    single = characters.single_character
    if single is not None:
        return antlr_literal(single)
    return "[" + "".join(character_set_part(part) for part in characters.parts) + "]"
