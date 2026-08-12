"""Character sets: the shapes written as bare text.

    a-z|A-Z|_       CHARACTER_SET   a set of several parts
    a  Letter  Lu   CHARACTER       a set of exactly one part

The two share a body and differ only in where they sit in the order:
`CHARACTER_SET` outranks a production of the same name, `CHARACTER` yields to
one. That is the whole of why `a-z|A-Z` is a set even where a production bears
that name, while a lone `Letter` is not.

What a set *is* — its parts, and how text reads as one — is in `charset`; the
category names it may use are in `categories`. This module is only the shapes
and what they build.
"""

from __future__ import annotations

import re

from ..semantics.macros import MacroDefinition
from ..semantics.shapes import MacroShape
from ..semantics.signatures import NAME_CHARACTER, make_shape
from ..itemizing.cst import Item
from ..systems.context import CallContext
from .rules import MacroCall, Rule
from .categories import CATEGORY_NAMES
from .charset import CharacterSet, parse_character_set

# -- the patterns -----------------------------------------------------------

#: One character as a signature spells it — `NAME_CHARACTER` is that alphabet,
#: and is used rather than restated so the two cannot drift apart. The
#: separator is included: `|` is an ordinary character where a part can be read
#: from it, and there is no escape that would say so instead.
_CHARACTER = NAME_CHARACTER

#: A category, longest name first, so `Lu` cannot win over `Lu…` — the names
#: come from the category table, which is the only place they are written down.
_CATEGORY = "|".join(
    re.escape(name) for name in sorted(CATEGORY_NAMES, key=len, reverse=True)
)

#: One part: a range, a category, or a single character, tried in that order.
_PART = rf"(?:{_CHARACTER}-{_CHARACTER}|{_CATEGORY}|{_CHARACTER})"

#: A set of two or more parts, and a set of exactly one. Both alternatives of
#: `|` — separator here, character inside a part — are open at once, and the
#: engine's backtracking settles it exactly as `parse_character_set` does: a
#: reading leaving no part empty, or no match at all. So `a||` is a set of two
#: and a lone `|` is a set of one, with nothing spelled out for either.
CHARACTER_SET_PATTERN = rf"{_PART}(?:\|{_PART})+"
CHARACTER_PATTERN = _PART


# -- what each call carries -------------------------------------------------


def _character_set_call_arguments(item: Item, match: re.Match[str]) -> dict[str, object]:
    """What a character set carries: the item, and the text that spells it."""
    return {"item": item, "text": item.text}


# -- the shapes -------------------------------------------------------------

CHARACTER_SET_SHAPE: MacroShape = make_shape(
    "character-set", CHARACTER_SET_PATTERN, _character_set_call_arguments
)
CHARACTER_SHAPE: MacroShape = make_shape(
    "character", CHARACTER_PATTERN, _character_set_call_arguments
)


# -- what they produce ------------------------------------------------------


def _make_character_set_macro(macro_shape: MacroShape) -> MacroDefinition:
    """One of the two character-set macros, naming itself in what it builds.

    The two share a body, but each still builds a call naming *itself* rather
    than one standing in for the other, so a node never misreports which macro
    made it. `character_set_matched_by` accepts either.
    """
    definition: MacroDefinition

    def produce_call(context: CallContext, item: Item, text: str) -> Rule | None:
        # The pattern is a shape and cannot compare the ends of a range, so `9-0`
        # reaches this point and is declined here. It goes on to be read as a
        # name, and is reported as an unknown one.
        if parse_character_set(text) is None:
            return None
        return MacroCall(macro=definition, item=item)

    definition = MacroDefinition(shape=macro_shape, produce_call=produce_call)
    return definition


CHARACTER_SET = _make_character_set_macro(CHARACTER_SET_SHAPE)
CHARACTER = _make_character_set_macro(CHARACTER_SHAPE)

#: The macros whose calls match one character from a set.
CHARACTER_MACROS = frozenset({CHARACTER_SET, CHARACTER})


def character_set_matched_by(node: Rule) -> CharacterSet | None:
    """The set a node matches one character from, or None for any other node."""
    if isinstance(node, MacroCall) and node.macro in CHARACTER_MACROS:
        return parse_character_set(node.item.text)
    return None
