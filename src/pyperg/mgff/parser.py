"""Reading of a Part 1 tree as Part 2 structure: CST -> AST.

Not implemented yet.

Line roles, fixed by the first item of a line:

    (none)  blank, ignored              |   >   attributes of the current macro
    #       comment, ignored            |   t   generation target
    d       macro definition            |   p   name prefix
    /       order-based alternative     |   |   length-based alternative
"""

from __future__ import annotations

from ..diagnostics.span import Span
from .ast import Attribute, Grammar, Macro, Scope
from .cst import File, Group, Item, Line


def parse(file: File) -> Grammar:
    """Read a lexed file as a grammar.

    Raises `SyntaxError_` on a line whose first item names no role, on an
    alternative with no macro to attach to, on mixed `/` and `|` markers, and on
    an alternative line following a `>` line.
    """
    # 1. Open the file scope over `file.lines`.
    # 2. Walk the lines, dispatching on the first item's text.
    # 3. Return the scope tree wrapped in a Grammar.
    raise NotImplementedError


def _parse_scope(lines: list[Line], kind: str, name: str, span: Span) -> Scope:
    """Read the lines of one scope, recursing into `t` and `p` groups.

    A macro stays "current" across comment lines, so `/`, `|` and `>` lines
    attach to the last `d` line seen in this scope.
    """
    raise NotImplementedError


def _parse_macro(line: Line) -> Macro:
    """Read a `d Head = Body` line.

    The head is the item after `d`; the separator is the first top-level `=`
    item, which must follow the head directly. Later `=` items are ordinary.
    """
    raise NotImplementedError


def _parse_head(item: Item) -> tuple[str, list[str]]:
    """Split a head item into a macro name and its parameter names.

    The text outside the groups is the name; each group declares one parameter,
    named by the single item inside it.
    """
    raise NotImplementedError


def _parse_attributes(line: Line) -> list[Attribute]:
    """Read the items of a `>` line as attributes: calls with or without arguments."""
    raise NotImplementedError


def _scope_body(line: Line) -> Group:
    """The group of a `t Name ( … )` or `p Prefix ( … )` line."""
    raise NotImplementedError
