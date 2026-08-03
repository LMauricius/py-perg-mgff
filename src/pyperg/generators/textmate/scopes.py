"""Token classes as TextMate scope names.

A TextMate grammar says what a token *is* by giving it a **scope name**: a
dotted path such as `keyword.control.toy`, ending in the language's own name. A
theme matches a scope by prefix and colours the longest prefix it knows, which
is why the path is ordered general to specific.

That makes the mapping from `utils.classes` straightforward — each class names
the prefix a theme will recognise — with two rules on top:

- **The language suffix.** Every scope ends in the language's identifier, so two
  languages that both have keywords can still be themed apart.
- **Extra classes stay in the path.** `class(Float Literal)` gives
  `constant.numeric.float.literal.toy`: the first class a theme knows decides
  the colour, and the rest survive for a theme that cares. This is what Kate's
  itemData name does, spelled the way TextMate spells it.

`Normal` maps to no scope at all. Unmatched text in TextMate is already the
editor's default colour, so a rule with no scope name is exactly right for
whitespace and punctuation — where Kate must name `dsNormal`, this names
nothing.
"""

from __future__ import annotations

import re

from ..utils.classes import FALLBACK_CLASS, canonical_class

#: Anything that may not appear inside one segment of a scope name.
_UNSAFE = re.compile(r"[^0-9a-z]+")

#: The scope prefix each shared class stands for. `Normal` maps to nothing,
#: which means the token keeps the editor's default colour.
SCOPE_PREFIXES: dict[str, str] = {
    "Normal": "",
    "Keyword": "keyword",
    "Function": "entity.name.function",
    "Variable": "variable.other",
    "ControlFlow": "keyword.control",
    "Operator": "keyword.operator",
    "BuiltIn": "support.function.builtin",
    "Extension": "support.other",
    "Preprocessor": "meta.preprocessor",
    "Attribute": "entity.other.attribute-name",
    "Char": "string.quoted.single",
    "SpecialChar": "constant.character.escape",
    "String": "string.quoted.double",
    "VerbatimString": "string.quoted.other",
    "SpecialString": "string.interpolated",
    "Import": "keyword.control.import",
    "DataType": "storage.type",
    "DecVal": "constant.numeric.integer",
    "BaseN": "constant.numeric.other",
    "Float": "constant.numeric.float",
    "Constant": "constant.language",
    "Comment": "comment",
    "Documentation": "comment.block.documentation",
    "Annotation": "entity.name.function.decorator",
    "CommentVar": "comment.block.documentation.variable",
    "RegionMarker": "comment.other.region",
    "Information": "comment.other.information",
    "Warning": "invalid.deprecated",
    "Alert": "invalid.illegal.alert",
    "Error": "invalid.illegal.error",
    "Others": "entity.other",
}


def scope_segment(text: str) -> str:
    """One class as a segment of a scope name.

    A scope name is lower case and separated by dots, so anything that would
    read as a separator becomes a hyphen, which TextMate allows.
    """
    return _UNSAFE.sub("-", text.lower()).strip("-")


def scope_for(classes: list[str], language: str) -> str | None:
    """The scope name a token's classes give it, or None when they give none.

    The first class naming a known prefix contributes it, every other class
    follows as a segment of its own, and the language's identifier ends the
    path. `Normal` alone contributes nothing, so the token stays unscoped.
    """
    prefix = ""
    extras: list[str] = []
    for name in classes:
        known = canonical_class(name)
        if known is not None:
            mapped = SCOPE_PREFIXES.get(known, "")
            # The first class a theme knows decides the colour; a later one has
            # to settle for being a segment, the way Kate joins itemData names.
            if mapped and not prefix:
                prefix = mapped
                continue
            if known == FALLBACK_CLASS:
                continue
        segment = scope_segment(name)
        if segment:
            extras.append(segment)
    if not prefix and not extras:
        return None
    return ".".join(part for part in (prefix, *extras, language) if part)


def region_scope(name: str, language: str) -> str:
    """The scope wrapping everything a bracketing production matches.

    `meta.` is the conventional home for a span that is a structure rather than
    a token; no theme colours it, and every editor can still ask what it is in.
    """
    return f"meta.{scope_segment(name)}.{language}"


def punctuation_scope(name: str, language: str, edge: str) -> str:
    """The scope for a bracket character itself, when its production names none.

    `edge` is `begin` or `end`. This is what VS Code's bracket matching and
    several themes look for.
    """
    return f"punctuation.section.{scope_segment(name)}.{edge}.{language}"
