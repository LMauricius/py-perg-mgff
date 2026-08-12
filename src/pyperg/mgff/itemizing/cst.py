"""The concrete syntax tree of specification Part 1.

The tree records the *shape* of a file and nothing else: how text splits into
lines, items, and groups. No node here carries grammatical meaning; that is the
job of `pyperg.grammar`.

Escapes are already resolved, so a `Text` node holds the characters a matcher
would see, not the spelling they had in the file.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ...diagnostics.span import Span
from .escapes import escape_character


@dataclass(slots=True)
class Text:
    """A run of literal characters, escapes resolved."""

    span: Span
    value: str


@dataclass(slots=True)
class Group:
    """A parenthesised region. Its contents are lines of their own."""

    span: Span
    lines: list[Line] = field(default_factory=list)


@dataclass(slots=True)
class Item:
    """One item: text and groups glued together, alternating.

    Whitespace separates items only outside parentheses, so however many spaces
    or newlines a group contains, the group and the text glued to it are one item.
    """

    span: Span
    parts: list[Text | Group] = field(default_factory=list)

    @property
    def text(self) -> str:
        """The item's text with its groups removed, e.g. `sep()by()` -> `sepby`."""
        return "".join(part.value for part in self.parts if isinstance(part, Text))

    @property
    def groups(self) -> list[Group]:
        """The item's groups, in order."""
        return [part for part in self.parts if isinstance(part, Group)]

    @property
    def is_bare_text(self) -> bool:
        """True when the item is text with no groups, e.g. `Digit`."""
        return bool(self.parts) and all(isinstance(part, Text) for part in self.parts)

    @property
    def is_bare_group(self) -> bool:
        """True when the item is a lone group, e.g. `( … )` — a subgroup."""
        return len(self.parts) == 1 and isinstance(self.parts[0], Group)


@dataclass(slots=True)
class Line:
    """A line: zero or more items. A line with no items is blank."""

    span: Span
    items: list[Item] = field(default_factory=list)

    @property
    def is_blank(self) -> bool:
        return not self.items


@dataclass(slots=True)
class Document:
    """A whole MGFF file: its top-level lines."""

    name: str
    lines: list[Line] = field(default_factory=list)


#: The characters a signature escapes. Without them the text `\(\)`, which is
#: two ordinary characters, would read as an empty group.
SIGNATURE_ESCAPES = set("\\()")


def signature_of(item: Item) -> str:
    """The lookup key of a head or a call: its text with the groups emptied.

    `sep(R)by(S)` and `sep(Ident = Expr)by(,)` both give `sep()by()`, so a call
    finds its macro by shape alone. Text is escaped, so the item `\\(` gives
    `\\(` and never the `()` of a real group.

    This is also the string a macro's shape is matched against, so a shape is
    recognised by the same key a name is looked up by.
    """
    out: list[str] = []
    for part in item.parts:
        if isinstance(part, Text):
            out.append(
                "".join(
                    "\\" + char if char in SIGNATURE_ESCAPES else char
                    for char in part.value
                )
            )
        else:
            out.append("()")
    return "".join(out)


def items_in_group(group: Group) -> list[Item]:
    """Every item of a group, its lines joined into one sequence.

    The line breaks inside a group are a matter of layout, so a subgroup and a
    choice option both read their contents this way.
    """
    return [item for line in group.lines for item in line.items]


def call_arguments_of(item: Item) -> list[list[Item]]:
    """The argument of each group of a call, as a sequence of items."""
    return [items_in_group(group) for group in item.groups]


def render_item(item: Item) -> str:
    """Render an item back into MGFF-like text, for dumps and error messages."""
    out: list[str] = []
    for part in item.parts:
        if isinstance(part, Text):
            out.append("".join(escape_character(c) for c in part.value))
        else:
            inner = " ".join(
                " ".join(render_item(inner_item) for inner_item in line.items)
                for line in part.lines
                if not line.is_blank
            )
            out.append(f"({inner})")
    return "".join(out)
