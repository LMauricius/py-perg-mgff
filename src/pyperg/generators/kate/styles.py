"""Token classes as Kate's default styles.

Kate gives every rule an *itemData*, and every itemData a *default style*, named
`dsKeyword`, `dsComment` and so on. A theme colours the default styles;
skylighting, which is what pandoc uses, maps them onto its own token types. The
default style is therefore the whole of what a highlighted token means here.

The classes themselves are the shared vocabulary of `utils.classes`, which is
Kate's list of default styles by origin; this module only says how one is
written into a syntax definition. The names below are re-exported so a reader
of Kate's own documentation finds them where they expect to.
"""

from __future__ import annotations

from ..utils.classes import (
    AUTOCLASS_SYNONYMS as AUTOCLASS_SYNONYMS,
    FALLBACK_CLASS as FALLBACK_STYLE,
    TOKEN_CLASSES as DEFAULT_STYLES,
    autoclass_for as autoclass_for,
    canonical_class as canonical_style,
    is_known_class as is_default_style,
)


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
