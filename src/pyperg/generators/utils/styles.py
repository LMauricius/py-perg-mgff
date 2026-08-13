"""What a highlighted token *looks like*, said in a way no backend owns.

A grammar says what a match is with `class(…)` and what it should look like with
`style(…)`. The two are separate on purpose: a class is the token's identity, and
a later phase matches on it; a style is a colour, and nothing matches on it.

    d Ident = Letter ( AlNum )*
            > class(Ident) style(Variable)

The vocabulary of styles is shared, and it is Kate's — its list of default styles
is the one every theme already knows, and the one skylighting maps onto pandoc's
token types. Kate turns a style into a `defStyleNum`, TextMate into a scope name.

A style is never derived and never assumed. A production that names none is
unstyled, which means the editor's ordinary text colour; a production that names
one the vocabulary does not hold is an error, since a misspelled style would
otherwise be silently invisible.

Further names after the first are **qualifiers**: they do not change the colour,
and survive into the output for a theme that cares to tell `Keyword Control` from
a plain `Keyword`.
"""

from __future__ import annotations

from ...diagnostics.errors import GeneratorError
from ...mgff.systems.grammar import Production

#: The styles a match may take, taken from Kate's default styles. A style means
#: the same thing to every backend.
HIGHLIGHT_STYLES: tuple[str, ...] = (
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

#: The style an unstyled match falls back to. It means "no particular
#: highlighting", and is what a backend writes where it must write something.
FALLBACK_STYLE = "Normal"

#: Lowered styles, so one matches whatever its capitalisation.
_BY_LOWER = {name.lower(): name for name in HIGHLIGHT_STYLES}


def is_known_style(name: str) -> bool:
    """Whether a name is one of the shared vocabulary."""
    return name.lower() in _BY_LOWER


def canonical_style(name: str) -> str | None:
    """A style as the vocabulary spells it, or None when it names none of them."""
    return _BY_LOWER.get(name.lower())


def styles_of(production: Production) -> list[str]:
    """The styles a production's match takes, empty when it asks for none.

    The first is the style proper and must name one of the vocabulary; the rest
    are qualifiers, kept as they were written.
    """
    styles = production.attributes.get("style")
    if styles is None:
        return []
    if not styles:
        raise GeneratorError(
            f"`style` on {production.name!r} needs a style, as in `> style(Keyword)`"
        )
    if not is_known_style(styles[0]):
        raise GeneratorError(
            f"{styles[0]!r} on {production.name!r} is no highlighting style. "
            f"The first argument of `style` names one of: {', '.join(HIGHLIGHT_STYLES)}."
        )
    return styles
