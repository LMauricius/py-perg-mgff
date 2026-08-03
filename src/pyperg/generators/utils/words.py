"""What counts as a word to a highlighter.

Both highlighting backends ask the same question of a fixed string, for
different reasons: Kate to decide whether `WordDetect` may match it, TextMate to
decide whether the pattern needs `\\b` around it. The answer is the same either
way, so it lives here.
"""

from __future__ import annotations


def is_word_character(char: str) -> bool:
    """Whether a highlighter would treat the character as part of a word."""
    return char.isalnum() or char == "_"


def is_word(text: str) -> bool:
    """Whether a fixed string is a word throughout."""
    return bool(text) and all(is_word_character(char) for char in text)


def is_word_bounded(text: str) -> bool:
    """Whether a fixed string begins and ends inside a word.

    A word boundary only exists next to a word character, so a string ending in
    punctuation would never be found between two of them.
    """
    return bool(text) and is_word_character(text[0]) and is_word_character(text[-1])
