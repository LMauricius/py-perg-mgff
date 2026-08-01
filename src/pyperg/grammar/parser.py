"""Reading of a Part 1 tree as Part 2 structure: lines -> scopes and macros.

A line's role is fixed by its first item, and a marker has that role only as a
complete first item of a line; elsewhere it is ordinary text.

    (none)  blank, ignored              |   >   attributes of the current macro
    #       comment, ignored            |   t   generation target
    d       macro definition            |   p   name prefix
    /       order-based alternative     |   |   length-based alternative

The items of a body, of an attribute line and of a parameter slot are left as
they were lexed. What an item *means* — a call, a subgroup, a character set — is
read later, by shape.
"""

from __future__ import annotations

from ..diagnostics.errors import SyntaxError_
from ..diagnostics.span import Position, Span
from ..mgff.cst import File, Group, Line
from .scope import Macro, Scope, Target, make_macro

# The first items that carry a role. Any other first item is an error.
MARKERS = frozenset({"#", "d", "/", "|", ">", "t", "p"})

CHOICE_MARKERS = frozenset({"/", "|"})

# The span of a file with no lines at all; nothing in it can be pointed at.
_EMPTY_SPAN = Span(Position(0, 1, 1), Position(0, 1, 1))


def marker_of(line: Line) -> str | None:
    """The role-carrying text of a line's first item, or None if it carries none.

    A marker is a complete first item of bare text, so the `/` of
    `/ Factor / Term` is a marker and the second `/` is not, and the head of
    `d ( x )` is not mistaken for one.
    """
    if line.is_blank:
        return None
    first = line.items[0]
    if not first.is_bare_text or first.text not in MARKERS:
        return None
    return first.text


def parse(file: File) -> Scope:
    """Read a lexed file as the scope it describes.

    Raises `SyntaxError_` on a line whose first item names no role, on an
    alternative with no macro to attach to, on mixed `/` and `|` markers, and on
    an alternative line following a `>` line. Raises `SemanticError` on a name
    defined twice in one scope.
    """
    root = Scope(span=_covering_span(file.lines), name="", parent=None)
    _parse_lines(file.lines, root)
    return root


def _covering_span(lines: list[Line]) -> Span:
    """The span from the first line to the last; a file with no lines is empty."""
    return Span.between(lines[0].span, lines[-1].span) if lines else _EMPTY_SPAN


def _parse_lines(lines: list[Line], scope: Scope) -> None:
    """Walk the lines of one scope, dispatching on each line's first item.

    The macro of the last `d` line stays current across comment lines, so the
    `/`, `|` and `>` lines that follow attach to it. `closed` records that a `>`
    line has been seen: attributes end the alternatives.
    """
    current: Macro | None = None
    closed = False

    for line in lines:
        marker = marker_of(line)
        rest = line.items[1:]

        # Blank and comment lines carry no role and do not end the macro.
        if line.is_blank or marker == "#":
            continue

        if marker is None:
            raise SyntaxError_(
                f"line starts with {line.items[0].text!r}, which names no role",
                line.items[0].span,
            )

        # `d Head = Body`: the macro the following lines attach to.
        if marker == "d":
            current, closed = _parse_definition(line, scope), False
            scope.define(current)

        # `/` and `|`: one more alternative of the current macro.
        elif marker in CHOICE_MARKERS:
            _add_option(current, marker, closed, line)

        # `>`: attributes, which end the alternatives.
        elif marker == ">":
            if current is None:
                raise SyntaxError_("attributes with no macro to attach to", line.items[0].span)
            current.attribute_lists.append(rest)
            closed = True

        # `t Name ( … )` and `p Prefix ( … )`: a nested scope.
        else:
            _parse_nested_scope(line, marker, scope)
            current, closed = None, False


# -- lines ------------------------------------------------------------------


def _parse_definition(line: Line, scope: Scope) -> Macro:
    """Read a `d Head = Body` line into a macro holding its first alternative.

    The head is the item after `d`, and the separator is the item right after it,
    which must be exactly `=`. Later `=` items are ordinary, and the head is read
    only after `d`, so a macro may bear any name, including a marker character.
    """
    items = line.items
    if len(items) < 2:
        raise SyntaxError_("a definition needs a head after `d`", items[0].span)
    if len(items) < 3 or not (items[2].is_bare_text and items[2].text == "="):
        raise SyntaxError_("a definition needs `=` right after the head", items[1].span)

    macro = make_macro(items[1], scope)
    macro.options.append(items[3:])
    return macro


def _add_option(current: Macro | None, marker: str, closed: bool, line: Line) -> None:
    """Attach one `/` or `|` line to the current macro as a further alternative.

    All alternatives of one macro use the same marker, and none may follow the
    macro's attributes.
    """
    where = line.items[0].span
    if current is None:
        raise SyntaxError_(f"alternative `{marker}` with no macro to attach to", where)
    if closed:
        raise SyntaxError_("an alternative may not follow a `>` line", where)
    if current.choice_symbol is not None and current.choice_symbol != marker:
        raise SyntaxError_(
            f"macro {current.name!r} mixes `{current.choice_symbol}` and `{marker}`; "
            "all alternatives of one macro use the same marker",
            where,
        )

    current.choice_symbol = marker
    current.options.append(line.items[1:])


def _parse_nested_scope(line: Line, marker: str, parent: Scope) -> None:
    """Read a `t Name ( … )` or `p Prefix ( … )` line and its contents.

    A prefix hands its names up to the parent once its own lines are read; a
    target keeps them. The name and the group may be written as two items or
    glued into one, so `p Util_ ( … )` and `p Util_( … )` are the same line.
    """
    name, body = _scope_head(line, marker)
    span = Span.between(line.items[0].span, body.span)

    if marker == "t":
        target = Target(span=span, name=name, parent=parent)
        _parse_lines(body.lines, target)
        parent.add_target(target)
    else:
        scope = Scope(span=span, name=name, parent=parent)
        _parse_lines(body.lines, scope)
        parent.add_subscope(scope)
        parent.absorb(scope)


def _scope_head(line: Line, marker: str) -> tuple[str, Group]:
    """The name and the body group of a `t` or `p` line, in either spelling."""
    kind = "target" if marker == "t" else "prefix"
    items = line.items[1:]

    # `t Name ( … )`: a bare name, then a lone group.
    if len(items) == 2 and items[0].is_bare_text and items[1].is_bare_group:
        return items[0].text, items[1].groups[0]

    # `t Name( … )`: the name glued to its group.
    if len(items) == 1 and len(items[0].groups) == 1 and items[0].text:
        return items[0].text, items[0].groups[0]

    raise SyntaxError_(f"a {kind} is written `{marker} Name ( … )`", line.items[0].span)
