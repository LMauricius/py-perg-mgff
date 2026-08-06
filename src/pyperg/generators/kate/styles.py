"""Highlighting styles as Kate's default styles.

Kate gives every rule an *itemData*, and every itemData a *default style*, named
`dsKeyword`, `dsComment` and so on. A theme colours the default styles;
skylighting, which is what pandoc uses, maps them onto its own token types. The
default style is therefore the whole of what a highlighted match looks like here.

The styles themselves are the shared vocabulary of `utils.styles`, which is
Kate's list of default styles by origin; this module only says how one is written
into a syntax definition. The names below are re-exported so a reader of Kate's
own documentation finds them where they expect to.
"""

from __future__ import annotations

from ..utils.styles import (
    FALLBACK_STYLE as FALLBACK_STYLE,
    HIGHLIGHT_STYLES as DEFAULT_STYLES,
    canonical_style as canonical_style,
    is_known_style as is_default_style,
    styles_of as styles_of,
)


def style_for(styles: list[str]) -> tuple[str, str]:
    """An itemData name and its `defStyleNum`, from a match's styles.

    The names are joined with `.` to name the itemData, so a theme can still tell
    `Keyword.Control` from a plain `Keyword`, and the first — which
    `utils.styles` has already checked names a default style — decides how the
    match is coloured. The qualifiers after it are kept in the name and nothing
    more.
    """
    if not styles:
        return FALLBACK_STYLE, f"ds{FALLBACK_STYLE}"
    name = ".".join(styles)
    return name, f"ds{canonical_style(styles[0]) or FALLBACK_STYLE}"
