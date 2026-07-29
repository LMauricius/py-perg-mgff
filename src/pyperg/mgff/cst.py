"""The concrete syntax tree of specification Part 1.

The tree records the *shape* of a file and nothing else: how text splits into
lines, items, and groups. No node here carries grammatical meaning; that is the
job of `pyperg.mgff.ast`.

Escapes are already resolved, so a `Text` node holds the characters a matcher
would see, not the spelling they had in the file.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..diagnostics.span import Span


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
        return "".join(p.value for p in self.parts if isinstance(p, Text))

    @property
    def groups(self) -> list[Group]:
        """The item's groups, in order."""
        return [p for p in self.parts if isinstance(p, Group)]

    @property
    def is_bare_text(self) -> bool:
        """True when the item is text with no groups, e.g. `Digit`."""
        return bool(self.parts) and all(isinstance(p, Text) for p in self.parts)

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
class File:
    """A whole MGFF file: its top-level lines."""

    name: str
    lines: list[Line] = field(default_factory=list)


def render_item(item: Item) -> str:
    """Render an item back into MGFF-like text, for dumps and error messages."""
    from .escapes import escape_char

    out: list[str] = []
    for part in item.parts:
        if isinstance(part, Text):
            out.append("".join(escape_char(c) for c in part.value))
        else:
            inner = " ".join(
                " ".join(render_item(i) for i in line.items)
                for line in part.lines
                if not line.is_blank
            )
            out.append(f"({inner})")
    return "".join(out)
