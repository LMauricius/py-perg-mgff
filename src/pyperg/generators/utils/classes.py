"""What a highlighted token *is*, said in a way no backend owns.

A grammar labels its tokens with `class(…)`, and every highlighting backend
needs the same labels: Kate turns them into default styles, TextMate into scope
names. The vocabulary is therefore shared, and it is Kate's — its list of
default styles is the one every theme already knows, and the one skylighting
maps onto pandoc's token types.

    d Ident = Alpha ( AlNum )*
            > class(Variable)

`autoclass` asks for the class to be derived from the macro's name instead, for
the common case where the name already says what the token is.
"""

from __future__ import annotations

import re
import sys

from ...diagnostics.errors import GeneratorError
from ...mgff.semantics.model import Production

#: The classes a token may carry, taken from Kate's default styles. A class
#: naming one of these means the same thing to every backend; one that names
#: none is kept as it was written, and a backend does what it can with it.
TOKEN_CLASSES: tuple[str, ...] = (
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

#: The class a token carries when it asks for none, and the one a derivation
#: falls back to. It means "no particular highlighting".
FALLBACK_CLASS = "Normal"

#: Names a grammar is likely to use for a token, and the class each one means.
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
    # punctuation and layout, which carry no highlighting of their own
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

#: Lowered classes, so one matches whatever its capitalisation.
_BY_LOWER = {name.lower(): name for name in TOKEN_CLASSES}


def is_known_class(name: str) -> bool:
    """Whether a class names one of the shared vocabulary."""
    return name.lower() in _BY_LOWER


def canonical_class(name: str) -> str | None:
    """A class as the vocabulary spells it, or None when it names none of them."""
    return _BY_LOWER.get(name.lower())


def classes_of(production: Production) -> list[str]:
    """The classes a production's token carries.

    `class(…)` names them outright. `autoclass` derives one from the macro's
    name. A production asking for neither is left unclassed, which is `Normal`.
    """
    if "class" in production.attributes:
        classes = production.attributes["class"]
        if not classes:
            raise GeneratorError(
                f"`class` on {production.name!r} needs at least one class, "
                "as in `> class(Keyword)`"
            )
        return classes
    if "autoclass" in production.attributes:
        return [autoclass_for(production.name)]
    return [FALLBACK_CLASS]


def autoclass_for(macro_name: str, warn: bool = True) -> str:
    """Derive a class from a macro's name.

    Four attempts, in order:

    1. the name *is* a class, as in `d Keyword = …`;
    2. the name is a known synonym, as in `d Ident = …` for a `Variable`;
    3. one of its words is, the last such word winning, so `LineComment` is a
       `Comment` and `HexNumber` is what `Number` is;
    4. nothing matched: `Normal`, and a line on stderr saying so.
    """
    exact = canonical_class(macro_name) or _synonym(macro_name)
    if exact is not None:
        return exact

    by_word = _last_matching_word(macro_name)
    if by_word is not None:
        return by_word

    if warn:
        print(
            f"pyperg: autoclass: no class matches macro {macro_name!r}; "
            f"using {FALLBACK_CLASS}. Write `> class(…)` to choose one.",
            file=sys.stderr,
        )
    return FALLBACK_CLASS


def _synonym(name: str) -> str | None:
    """The class a known token name stands for, ignoring case and separators."""
    return AUTOCLASS_SYNONYMS.get(name.lower().replace("-", "_"))


def _last_matching_word(name: str) -> str | None:
    """The class named by the last word of a name that names one.

    A macro name is read as words the way it is written: `LineComment`,
    `line_comment` and `line-comment` all split the same way. The last word
    wins because it says what the token *is*, the ones before it only qualify
    it — a `HexNumber` is a number, however it is spelled.
    """
    for word in reversed(words_of(name)):
        found = canonical_class(word) or _synonym(word)
        if found is not None:
            return found
    return None


def words_of(name: str) -> list[str]:
    """A macro name split into words, at separators and at case changes."""
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", name)
    return [word for word in re.split(r"[^0-9A-Za-z]+", spaced) if word]
