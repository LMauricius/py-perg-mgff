"""Rule trees and character sets as regular expressions.

The dialect produced here is the PCRE-compatible one that Qt's
`QRegularExpression` and the `regex-pcre` engine behind skylighting both read,
so a Unicode category becomes `\\p{Lu}` and a group is always non-capturing.

Two things a regular expression cannot express are reported rather than faked:

- **Recursion.** A production that reaches itself has no regular form, so
  `regex_of` returns None and the backend falls back to whatever it uses for
  rules that nest.
- **Longest-match choice.** Alternation in a regular expression takes the first
  option that succeeds, which is MGFF's `/`. For `|`, whose match is the longest,
  the options are emitted longest fixed prefix first. That is exact whenever the
  options have fixed lengths — the usual case, `<=` before `<` — and an
  approximation otherwise.

A `MacroCall` of any macro but a character set belongs to whoever defined that
macro, so `regex_of` takes an optional `emit` for those and returns None without
one.

A backend that solves its own recursion — the regex backend does, by Arden's
rule — hands the patterns it has already worked out to `regex_of` as `patterns`,
and builds the rest with `concatenation`, `alternation` and `atom`, which bracket
what they join exactly as `regex_of` does.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping

from ...mgff.common.characters import character_set_of
from ...mgff.common.charset import CharacterPart, CharacterSet
from ...mgff.common.rules import Choice, MacroCall, Rule, Repetition, Sequence
from ...mgff.semantics.model import Production

#: Characters that need a backslash outside a character class.
METACHARACTERS = set(r".^$*+?()[]{}|\\")

#: Characters that need a backslash inside a character class.
CLASS_METACHARACTERS = set(r"^]\-")

Lookup = Callable[[str], Production | None]

#: Emits a macro call the backend registered itself, given the call and a way to
#: turn its arguments into patterns. None means "no regular form".
Emit = Callable[[MacroCall, Callable[[Rule], str | None]], str | None]


# -- characters ------------------------------------------------------------


def escape_character(char: str) -> str:
    """Escape one character for use outside a character class."""
    if char in METACHARACTERS:
        return "\\" + char
    return _control_escape(char) or char


def escape_in_class(char: str) -> str:
    """Escape one character for use inside `[ … ]`."""
    if char in CLASS_METACHARACTERS:
        return "\\" + char
    return _control_escape(char) or char


def _control_escape(char: str) -> str | None:
    """The readable spelling of a control character, or None if it needs none."""
    known = {"\n": "\\n", "\r": "\\r", "\t": "\\t", "\f": "\\f", "\v": "\\v"}
    if char in known:
        return known[char]
    if ord(char) < 0x20 or ord(char) == 0x7F:
        return f"\\x{{{ord(char):02x}}}"
    return None


def part_pattern(part: CharacterPart) -> str:
    """One part of a character set, as it appears inside `[ … ]`."""
    if part.kind == "character":
        return escape_in_class(part.value)
    if part.kind == "range":
        return f"{escape_in_class(part.value)}-{escape_in_class(part.high)}"
    return f"\\p{{{part.value}}}"


def character_class(characters: CharacterSet) -> str:
    """A character set as a pattern matching one character.

    A lone character needs no brackets, and neither does a lone category, so the
    common cases stay readable.
    """
    parts = characters.parts
    if len(parts) == 1:
        only = parts[0]
        if only.kind == "character":
            return escape_character(only.value)
        if only.kind == "category":
            return f"\\p{{{only.value}}}"
    return "[" + "".join(part_pattern(part) for part in parts) + "]"


# -- rule trees ------------------------------------------------------------


def regex_of(
    node: Rule,
    lookup: Lookup,
    emit: Emit | None = None,
    patterns: Mapping[str, str] | None = None,
) -> str | None:
    """A rule tree as a regular expression, or None when it has no regular form.

    A reference is answered by `patterns` when it names one, and inlined through
    `lookup` otherwise; a reference that leads back to itself, or to a name
    neither knows, gives None. `emit` handles the macro calls this module knows
    nothing of.
    """
    return _regex(node, lookup, emit, patterns or {}, seen=frozenset())


def _regex(
    node: Rule,
    lookup: Lookup,
    emit: Emit | None,
    patterns: Mapping[str, str],
    seen: frozenset[str],
) -> str | None:
    def inner(sub: Rule) -> str | None:
        return _regex(sub, lookup, emit, patterns, seen)

    if isinstance(node, MacroCall):
        characters = character_set_of(node)
        if characters is not None:
            return character_class(characters)
        if emit is None:
            return None
        return emit(node, inner)

    if isinstance(node, Sequence):
        pieces: list[str] = []
        for item in node.items:
            piece = inner(item)
            if piece is None:
                return None
            pieces.append(piece)
        return concatenation(pieces)

    if isinstance(node, Repetition):
        body = inner(node.body)
        if body is None:
            return None
        return atom(body) + _quantifier(node.minimum, node.maximum)

    if isinstance(node, Choice):
        options: list[str] = []
        for option in node.options:
            pattern = inner(option)
            if pattern is None:
                return None
            options.append(pattern)
        return alternation(options, node.symbol)

    # A reference: the pattern already worked out for it, or the production it
    # names, inlined once.
    if node.name in patterns:
        return patterns[node.name]
    if node.name in seen:
        return None
    production = lookup(node.name)
    if production is None:
        return None
    return _regex(production.rule, lookup, emit, patterns, seen | {node.name})


# -- putting patterns together ---------------------------------------------


def concatenation(pieces: list[str]) -> str:
    """Patterns matched one after another, each bracketed where it must be."""
    return "".join(_grouped_for_sequence(piece) for piece in pieces)


def alternation(options: list[str], symbol: str = "/") -> str:
    """Options as one alternation, ordered by the choice's preference mode.

    `/` keeps the written order. `|` wants the longest match, which alternation
    cannot express, so the longest fixed option goes first — enough to make `<=`
    win over `<`.
    """
    if len(options) == 1:
        return options[0]
    ordered = options if symbol == "/" else sorted(options, key=_fixed_length, reverse=True)
    return "(?:" + "|".join(ordered) + ")"


def _quantifier(minimum: int, maximum: int | None) -> str:
    """The suffix repeating an atom between `minimum` and `maximum` times."""
    if (minimum, maximum) == (0, 1):
        return "?"
    if (minimum, maximum) == (0, None):
        return "*"
    if (minimum, maximum) == (1, None):
        return "+"
    if maximum is None:
        return f"{{{minimum},}}"
    if minimum == maximum:
        return f"{{{minimum}}}"
    return f"{{{minimum},{maximum}}}"


def _class_end(pattern: str, start: int) -> int:
    """Where the character class opening at `start` closes, or -1 if it does not.

    A `]` is the closing bracket everywhere except in two places: straight after
    the opening bracket, or straight after a negating `^`, where it is a literal
    instead. `escape_in_class` never writes either, but a pattern a caller
    assembled itself may.
    """
    index = start + 1
    if pattern[index : index + 1] == "^":
        index += 1
    if pattern[index : index + 1] == "]":
        index += 1
    while index < len(pattern):
        if pattern[index] == "\\":
            index += 2
            continue
        if pattern[index] == "]":
            return index
        index += 1
    return -1


def _fixed_length(pattern: str) -> int:
    """How many characters a pattern matches when that number is fixed, else -1.

    A plain character, an escape and a character class each match exactly one;
    an anchor matches none. Anything whose length depends on the input — a
    quantifier, an alternation, a group — has no fixed length, and answering -1
    sorts it behind every option that does: a variable-length option tried first
    would match short and take the whole choice with it.

    The scan is what makes this exact: a metacharacter only means what it says
    where it is neither escaped nor inside a class, so the literal `\\+` is a
    character like any other, `[+*]` is one character out of two, and `\\p{Lu}`
    is one character however long its name is. Reading for those characters
    without scanning would call all three of them variable-length, and a choice
    of `\\+\\+` against `\\+` would then be ordered by nothing at all.
    """
    length, index = 0, 0
    while index < len(pattern):
        char = pattern[index]
        if char == "\\":
            if index + 1 >= len(pattern):
                return -1  # a trailing backslash is no pattern
            # A Unicode category carries its name in braces and is still one
            # character; every other escape is the two characters it is written as.
            if pattern[index + 1] in "pP" and pattern[index + 2 : index + 3] == "{":
                closing = pattern.find("}", index + 3)
                if closing == -1:
                    return -1
                index = closing + 1
            else:
                index += 2
            length += 1
        elif char == "[":
            closing = _class_end(pattern, index)
            if closing == -1:
                return -1
            index = closing + 1
            length += 1
        elif char in "()|*+?{":
            return -1
        elif char in "^$":
            index += 1  # an anchor matches no characters
        else:
            index += 1
            length += 1
    return length


def atom(pattern: str) -> str:
    """A pattern wrapped so a quantifier applies to the whole of it."""
    return pattern if _is_atomic(pattern) else f"(?:{pattern})"


def _grouped_for_sequence(pattern: str) -> str:
    """A pattern wrapped only where concatenation would change its meaning.

    `alternation` already brackets what it builds, so this is about nothing
    else; the check stays for patterns a caller assembled itself.
    """
    return f"(?:{pattern})" if "|" in pattern and not _is_atomic(pattern) else pattern


def _is_atomic(pattern: str) -> bool:
    """Whether a quantifier may follow the pattern without brackets."""
    if len(pattern) == 1:
        return True
    if len(pattern) == 2 and pattern[0] == "\\":
        return True
    if pattern.startswith("\\p{") and pattern.endswith("}") and "}" not in pattern[3:-1]:
        return True
    # A single bracketed group: balanced, and closing only at the very end.
    if pattern[0] in "([" and pattern[-1] in ")]":
        depth, index = 0, 0
        while index < len(pattern):
            char = pattern[index]
            if char == "\\":
                index += 2
                continue
            if char in "([":
                depth += 1
            elif char in ")]":
                depth -= 1
                if depth == 0 and index != len(pattern) - 1:
                    return False
            index += 1
        return depth == 0
    return False
