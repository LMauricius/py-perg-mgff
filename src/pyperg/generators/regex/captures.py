"""The capture group this backend adds to the common vocabulary.

    name:( rule )   a group whose match is remembered under `name`
    :( rule )       a group whose match is remembered by position

Nothing in MGFF says what `name:( … )` means — it is an ordinary item, whose
signature is `name:()` — so the shape is registered here and read back from the
`MacroCall` it builds. The call carries the rule it wraps as its one argument,
so the rest of the backend walks it like any other node and only the emitter
knows a group is there.
"""

from __future__ import annotations

import re

from ...mgff.grammar.macros import MacroDefinition
from ...mgff.grammar.shapes import MacroShape
from ...mgff.grammar.signatures import NAME_CHARACTER, shape
from ...mgff.lexing.cst import Item
from ...mgff.common.rules import MacroCall, Rule
from ...mgff.semantics.context import CallContext

#: A name, then a colon, then exactly one group. The name may be empty, which is
#: how an unnamed group is written.
CAPTURE_PATTERN = rf"(?P<name>{NAME_CHARACTER}*):\(\)"

#: What a capture group may be called, so the name survives into the output.
VALID_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def _capture_args(item: Item, match: re.Match[str]) -> dict[str, object]:
    """What a capture group carries: the item, and the rule inside its group."""
    return {"item": item, "body": item.groups[0]}


CAPTURE_SHAPE: MacroShape = shape("capture", CAPTURE_PATTERN, _capture_args)


def _capture(context: CallContext, item: Item, body: Rule) -> Rule:
    """A capture group, kept as a call so the emitter can bracket it."""
    return MacroCall(macro=CAPTURE, item=item, arguments=[body])


CAPTURE = MacroDefinition(shape=CAPTURE_SHAPE, produce_call=_capture)


def is_capture(node: Rule) -> bool:
    """Whether a node is a call of this backend's capture group."""
    return isinstance(node, MacroCall) and node.macro is CAPTURE


def capture_name(node: MacroCall) -> str:
    """What a capture group is called, `""` when it was written unnamed.

    The item's text is the name and the colon, since the text of an item leaves
    its groups out.
    """
    return node.item.text.removesuffix(":")
