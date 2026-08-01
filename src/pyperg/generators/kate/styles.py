"""Token classes and how they become Kate's default styles.

Kate gives every rule an *itemData*, and every itemData a *default style*, named
`dsKeyword`, `dsComment` and so on. A theme colours the default styles;
skylighting, which is what pandoc uses, maps them onto its own token types. The
default style is therefore the whole of what a highlighted token means, and the
`class` attribute is how a grammar picks one.

    d Ident = Alpha ( AlNum )*
            > class(Variable)

`autoclass` asks for the class to be derived from the macro's name instead, for
the common case where the name already says what the token is.
"""

from __future__ import annotations

import re
import sys

#: Kate's default styles, without their `ds` prefix. A class naming one of these
#: is passed straight through, so `class(Keyword)` gives `defStyleNum="dsKeyword"`.
DEFAULT_STYLES: tuple[str, ...] = (
    "Normal",
    "Keyword",
    "Function",
    "Variable",
    "ControlFlow",
    "Operator",
    "BuiltIn",
    "Extension",
    "Preprocessor",
    "Attribute",
    "Char",
    "SpecialChar",
    "String",
    "VerbatimString",
    "SpecialString",
    "Import",
    "DataType",
    "DecVal",
    "BaseN",
    "Float",
    "Constant",
    "Comment",
    "Documentation",
    "Annotation",
    "CommentVar",
    "RegionMarker",
    "Information",
    "Warning",
    "Alert",
    "Error",
    "Others",
)

#: The style a class falls back to when it names none of the above.
FALLBACK_STYLE = "Normal"

#: Names a grammar is likely to use for a token, and the style each one means.
#: Consulted by `autoclass` only; an explicit `class` is never rewritten.
AUTOCLASS_SYNONYMS: dict[str, str] = {
    # identifiers and names
    "ident": "Variable",
    "identifier": "Variable",
    "name": "Variable",
    "symbol": "Variable",
    "var": "Variable",
    # numbers
    "number": "DecVal",
    "num": "DecVal",
    "int": "DecVal",
    "integer": "DecVal",
    "digit": "DecVal",
    "digits": "DecVal",
    "real": "Float",
    "double": "Float",
    "hex": "BaseN",
    "oct": "BaseN",
    "octal": "BaseN",
    "bin": "BaseN",
    "binary": "BaseN",
    # text
    "str": "String",
    "text": "String",
    "quoted": "String",
    "escape": "SpecialChar",
    "character": "Char",
    "charlit": "Char",
    # words
    "kw": "Keyword",
    "keywords": "Keyword",
    "reserved": "Keyword",
    "builtin": "BuiltIn",
    "type": "DataType",
    "datatype": "DataType",
    "func": "Function",
    "fun": "Function",
    "call": "Function",
    "const": "Constant",
    "literal": "Constant",
    # punctuation and layout, which Kate leaves unstyled
    "op": "Operator",
    "ops": "Operator",
    "punct": "Normal",
    "punctuation": "Normal",
    "space": "Normal",
    "spaces": "Normal",
    "whitespace": "Normal",
    "ws": "Normal",
    "newline": "Normal",
    "lparen": "Normal",
    "rparen": "Normal",
    "lbrace": "Normal",
    "rbrace": "Normal",
    "lbracket": "Normal",
    "rbracket": "Normal",
    "comma": "Normal",
    "semicolon": "Normal",
    # the rest
    "doc": "Documentation",
    "docs": "Documentation",
    "comments": "Comment",
    "line_comment": "Comment",
    "block_comment": "Comment",
    "pragma": "Preprocessor",
    "directive": "Preprocessor",
    "include": "Import",
    "use": "Import",
    "label": "Others",
    "tag": "Keyword",
    "attr": "Attribute",
    "flow": "ControlFlow",
    "control": "ControlFlow",
}

#: Lowered default styles, so a class matches whatever its capitalisation.
_STYLES_BY_LOWER = {style.lower(): style for style in DEFAULT_STYLES}


def is_default_style(name: str) -> bool:
    """Whether a class names one of Kate's default styles."""
    return name.lower() in _STYLES_BY_LOWER


def canonical_style(name: str) -> str | None:
    """A class as Kate spells the style, or None when it names no style."""
    return _STYLES_BY_LOWER.get(name.lower())


def autoclass_for(macro_name: str, warn: bool = True) -> str:
    """Derive a class from a macro's name.

    Four attempts, in order:

    1. the name *is* a default style, as in `d Keyword = …`;
    2. the name is a known synonym, as in `d Ident = …` for a `Variable`;
    3. one of its words is, the last such word winning, so `LineComment` is a
       `Comment` and `HexNumber` is what `Number` is;
    4. nothing matched: `Normal`, and a line on stderr saying so.
    """
    exact = canonical_style(macro_name) or _synonym(macro_name)
    if exact is not None:
        return exact

    by_word = _last_matching_word(macro_name)
    if by_word is not None:
        return by_word

    if warn:
        print(
            f"pyperg: autoclass: no style matches macro {macro_name!r}; "
            f"using {FALLBACK_STYLE}. Write `> class(…)` to choose one.",
            file=sys.stderr,
        )
    return FALLBACK_STYLE


def _synonym(name: str) -> str | None:
    """The style a known token name stands for, ignoring case and separators."""
    return AUTOCLASS_SYNONYMS.get(name.lower().replace("-", "_"))


def _last_matching_word(name: str) -> str | None:
    """The style named by the last word of a name that names one.

    A macro name is read as words the way it is written: `LineComment`,
    `line_comment` and `line-comment` all split the same way. The last word
    wins because it says what the token *is*, the ones before it only qualify
    it — a `HexNumber` is a number, however it is spelled.
    """
    for word in reversed(_words(name)):
        style = canonical_style(word) or _synonym(word)
        if style is not None:
            return style
    return None


def _words(name: str) -> list[str]:
    """A macro name split into words, at separators and at case changes."""
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", name)
    return [word for word in re.split(r"[^0-9A-Za-z]+", spaced) if word]


def style_for(classes: list[str]) -> tuple[str, str]:
    """An itemData name and its `defStyleNum`, from a token's classes.

    The classes are joined with `.` to name the itemData, so a theme can still
    tell `Keyword.Control` from a plain `Keyword`, and the first class naming a
    default style decides how the token is coloured. Classes naming no style are
    kept in the name and nothing more.
    """
    if not classes:
        return FALLBACK_STYLE, f"ds{FALLBACK_STYLE}"
    name = ".".join(classes)
    style = next(
        (canonical_style(cls) for cls in classes if is_default_style(cls)),
        FALLBACK_STYLE,
    )
    return name, f"ds{style}"
