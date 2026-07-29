"""Escapes (specification Part 1)."""

import pytest

from pyperg.diagnostics.errors import LexError
from pyperg.mgff.escapes import read_escape


def resolve(text: str) -> str:
    """The character an escape denotes, checking that the whole text is consumed."""
    char, end = read_escape(text, 0)
    assert end == len(text)
    return char


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (r"\(", "("),
        (r"\)", ")"),
        ("\\\\", "\\"),
        (r"\_", " "),
        (r"\0", "\0"),
        (r"\n", "\n"),
        (r"\t", "\t"),
        (r"\v", "\v"),
        (r"\x28", "("),
        ("\\u00e9", "é"),
        (r"\U0001F600", "\U0001f600"),
        (r"\<GREEK_SMALL_LETTER_ALPHA>", "α"),
    ],
)
def test_valid_escapes(text, expected):
    assert resolve(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        r"\*",  # not in the closed set
        "\\ ",  # whitespace is written \_ or \t
        "\\\t",
        r"\x2",  # too few digits
        r"\xzz",
        r"\uD800",  # surrogate
        r"\U00110000",  # above U+10FFFF
        r"\<NOT_A_CHARACTER_NAME>",
        r"\<unterminated",
        "\\",
    ],
)
def test_invalid_escapes(text):
    with pytest.raises(LexError):
        read_escape(text, 0)


def test_escape_carries_no_role():
    """An escaped parenthesis is text, never the opening of a group."""
    assert resolve(r"\x28") == "("
