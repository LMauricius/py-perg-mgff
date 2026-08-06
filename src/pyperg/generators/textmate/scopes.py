"""Highlighting styles as TextMate scope names.

A TextMate grammar says what a match looks like by giving it a **scope name**: a
dotted path such as `keyword.control.toy`, ending in the language's own name. A
theme matches a scope by prefix and colours the longest prefix it knows, which
is why the path is ordered general to specific.

That makes the mapping from `utils.styles` straightforward — each style names
the prefix a theme will recognise — with two rules on top:

- **The language suffix.** Every scope ends in the language's identifier, so two
  languages that both have keywords can still be themed apart.
- **Qualifiers stay in the path.** `style(Float Literal)` gives
  `constant.numeric.float.literal.toy`: the style decides the colour, and the
  qualifiers survive for a theme that cares. This is what Kate's itemData name
  does, spelled the way TextMate spells it.

`Normal` maps to no scope at all, and so does a match with no style. Unmatched
text in TextMate is already the editor's default colour, so a rule with no scope
name is exactly right for whitespace and punctuation — where Kate must name
`dsNormal`, this names nothing.
"""

from __future__ import annotations

import re

from ..utils.styles import FALLBACK_STYLE, canonical_style

#: Anything that may not appear inside one segment of a scope name.
_UNSAFE = re.compile(r"[^0-9a-z]+")

#: The scope prefix each shared style stands for. `Normal` maps to nothing,
#: which means the match keeps the editor's default colour.
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
    """One style name as a segment of a scope name.

    A scope name is lower case and separated by dots, so anything that would
    read as a separator becomes a hyphen, which TextMate allows.
    """
    return _UNSAFE.sub("-", text.lower()).strip("-")


def scope_for(styles: list[str], language: str) -> str | None:
    """The scope name a match's styles give it, or None when they give none.

    The first style naming a known prefix contributes it, every qualifier
    follows as a segment of its own, and the language's identifier ends the
    path. `Normal` alone contributes nothing, so the match stays unscoped.
    """
    prefix = ""
    extras: list[str] = []
    for name in styles:
        known = canonical_style(name)
        if known is not None:
            mapped = SCOPE_PREFIXES.get(known, "")
            # The style a theme knows decides the colour; a qualifier has to
            # settle for being a segment, the way Kate joins itemData names.
            if mapped and not prefix:
                prefix = mapped
                continue
            if known == FALLBACK_STYLE:
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
