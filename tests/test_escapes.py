"""Escapes (specification Part 1)."""

import pytest

from pyperg.diagnostics.errors import ItemizationError
from pyperg.mgff.itemizing.escapes import read_escape

def escaped_character(text: str) -> str:
    """The character an escape denotes, checking that the whole text is consumed."""
    character, end = read_escape(text, 0)
    assert end == len(text)
    return character


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
    assert escaped_character(text) == expected


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
    with pytest.raises(ItemizationError):
        read_escape(text, 0)


def test_escape_carries_no_role():
    """An escaped parenthesis is text, never the opening of a group."""
    assert escaped_character(r"\x28") == "("


def test_a_named_sequence_is_not_one_character():
    """`\\<NAME>` denotes one character; a name standing for several is rejected."""
    with pytest.raises(ItemizationError, match="sequence of 3 characters"):
        read_escape(r"\<KEYCAP_NUMBER_SIGN>", 0)
