"""The abstract syntax tree of specification Part 2: what the lines mean.

A line's role is fixed by its first item, an item's role by its shape. This
module holds the result of that reading; the reading itself is in
`pyperg.mgff.parser`, and the interpretation of item shapes in
`pyperg.semantics.shapes`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from ..diagnostics.span import Span
from .cst import Item


class Preference(Enum):
    """How a macro chooses among its alternatives."""

    ORDER = "/"  # the first alternative that succeeds
    LENGTH = "|"  # the alternative consuming the most input; ties to the earliest


@dataclass(slots=True)
class Alternative:
    """One alternative of a macro: a sequence of items matched in order."""

    span: Span
    items: list[Item] = field(default_factory=list)


@dataclass(slots=True)
class Attribute:
    """A generator-specific attribute from a `>` line, e.g. `token`, `skip(false)`."""

    span: Span
    name: str
    arguments: list[list[Item]] = field(default_factory=list)


@dataclass(slots=True)
class Parameter:
    """A parameter slot declared by a group in a macro head."""

    span: Span
    name: str


@dataclass(slots=True)
class Macro:
    """A macro definition: `d Head = Body`, plus its later alternatives.

    `name` is the head's text with the parameter slots removed, so the head
    `sep(R)by(S)` gives the name `sepby` and the parameters `R` and `S`.
    `qualified_name` carries the prefixes of the enclosing `p` blocks.
    """

    span: Span
    name: str
    qualified_name: str
    parameters: list[Parameter] = field(default_factory=list)
    alternatives: list[Alternative] = field(default_factory=list)
    preference: Preference = Preference.ORDER
    attributes: list[Attribute] = field(default_factory=list)


@dataclass(slots=True)
class Scope:
    """A region holding macros and further scopes.

    A target (`t Name ( … )`) is a generation phase; a prefix (`p Prefix ( … )`)
    prepends text to the names defined directly inside it. The outermost scope is
    neither, and its macros are visible to every target.
    """

    span: Span
    kind: str  # "file", "target" or "prefix"
    name: str  # the target's name, the prefix's text, or "" for the file scope
    macros: list[Macro] = field(default_factory=list)
    children: list[Scope] = field(default_factory=list)


@dataclass(slots=True)
class Grammar:
    """A whole MGFF file, read as Part 2 defines it."""

    name: str
    root: Scope
