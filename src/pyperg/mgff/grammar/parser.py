"""Reading of a Part 1 tree as Part 2 structure: lines -> scopes and macros.

A line's role is fixed by its first item, and a marker has that role only as a
complete first item of a line; elsewhere it is ordinary text.

    (none)  blank, ignored              |   >   attributes
    #       comment, ignored            |   t   generation target
    d       macro definition            |   p   name prefix
    /       order-based alternative     |   |   length-based alternative

A `>` line attaches to the macro above it. Written before any definition or
nested scope it has no macro to attach to, and describes the enclosing scope
instead — the file, the target or the prefix.

The items of a body, of an attribute line and of a parameter slot are left as
they were lexed. What an item *means* — a call, a subgroup, a character set — is
read later, by shape.

Parsing does not decide what a macro produces. Every `d` line is read into a
`MacroSource` and handed to the **factory** the caller supplied, whose result
becomes the `produce_call` of the definition filed in the scope. A caller
building rule trees and one emitting a regular expression share every line of
this module and differ only in that function.
"""

from __future__ import annotations

from collections.abc import Callable

from ...diagnostics.errors import SyntaxError_
from ...diagnostics.span import Position, Span
from ..lexing.cst import File, Group, Line
from .macros import MacroDefinition, ProduceCall
from .scope import MacroSource, Scope, TargetScope, make_source
from .signatures import signature_to_shape

#: Builds what a call of one `d` definition produces. Called once per definition,
#: with the line as it was written, after all of its alternatives are in.
ProduceCallFactory = Callable[[MacroSource], ProduceCall]

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


def parse(file: File, factory: ProduceCallFactory | None = None) -> Scope:
    """Read a lexed file as the scope it describes.

    `factory` says what a call of each definition produces; without one the
    definitions are filed with a `produce_call` that raises, which is enough for
    reading a file's structure and no use for generating from it.

    Raises `SyntaxError_` on a line whose first item names no role, on an
    alternative with no macro to attach to, on mixed `/` and `|` markers, on an
    alternative line following a `>` line, and on a scope's own attributes
    written after its first definition. Raises `SemanticError` on a name defined
    twice in one scope.
    """
    root = Scope(span=_covering_span(file.lines), name="", parent=None)
    _parse_lines(file.lines, root, factory or _no_factory)
    return root


def _no_factory(source: MacroSource) -> ProduceCall:
    """The stand-in for a caller that only wants the structure of a file."""

    def produce_call(**arguments: object) -> object:
        raise SyntaxError_(
            f"{source.name!r} was read without a generator to give it meaning",
            source.span,
        )

    return produce_call


def _covering_span(lines: list[Line]) -> Span:
    """The span from the first line to the last; a file with no lines is empty."""
    return Span.between(lines[0].span, lines[-1].span) if lines else _EMPTY_SPAN


def _parse_lines(
    lines: list[Line], scope: Scope, custom_produce_call_factory: ProduceCallFactory
) -> None:
    """Walk the lines of one scope, dispatching on each line's first item.

    The macro of the last `d` line stays current across comment lines, so the
    `/`, `|` and `>` lines that follow attach to it. `closed` records that a `>`
    line has been seen: attributes end the alternatives. `opened` records that
    the scope has a body, after which a `>` line belongs to a macro or to
    nothing: the scope's own attributes are written above everything else.
    """
    current: MacroSource | None = None
    closed = False
    opened = False
    read: list[MacroSource] = []

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

        # `d Head = Body`: the macro the following lines attach to. A definition
        # separated by `>` has attributes already, so its alternatives are closed.
        if marker == "d":
            current = _parse_definition(line, scope)
            closed = bool(current.attribute_lists)
            opened = True
            scope.reserve(current)
            read.append(current)

        # `/` and `|`: one more alternative of the current macro.
        elif marker in CHOICE_MARKERS:
            _add_option(current, marker, closed, line)

        # `>`: attributes of the macro above, which end its alternatives. With no
        # macro above them they are the scope's own, and belong at its very top.
        elif marker == ">":
            if current is not None:
                current.attribute_lists.append(rest)
                closed = True
            elif opened:
                raise SyntaxError_(
                    "attributes with no macro to attach to; a scope's own "
                    "attributes are written above its first definition",
                    line.items[0].span,
                )
            else:
                scope.attribute_list.extend(rest)

        # `t Name ( … )` and `p Prefix ( … )`: a nested scope.
        else:
            _parse_nested_scope(line, marker, scope, custom_produce_call_factory)
            current, closed, opened = None, False, True

    # The alternatives of a `d` line arrive one line at a time, so a definition
    # is built only once the whole scope has been read.
    for source in read:
        scope.define(source, _source_to_definition(source, custom_produce_call_factory))


def _source_to_definition(
    source: MacroSource, custom_produce_call_factory: ProduceCallFactory
) -> MacroDefinition:
    """Build one definition: its shape from the head, its body from the factory."""
    return MacroDefinition(
        shape=signature_to_shape(source.signature, source.parameters),
        produce_call=custom_produce_call_factory(source),
    )


# -- lines ------------------------------------------------------------------


def _parse_definition(line: Line, scope: Scope) -> MacroSource:
    """Read a `d Head = Body` line into a macro holding its first alternative.

    The head is the item after `d`, and the separator is the item right after it,
    which must be exactly `=`. Later `=` items are ordinary, and the head is read
    only after `d`, so a macro may bear any name, including a marker character.

    `d Head > Attributes` separates with `>` instead: the macro has no options at
    all, and the rest of the line is its first attribute list. Such a macro
    matches nothing on its own, which is how a named list of attributes is written.
    """
    items = line.items
    if len(items) < 2:
        raise SyntaxError_("a definition needs a head after `d`", items[0].span)
    if len(items) < 3 or not (items[2].is_bare_text and items[2].text in ("=", ">")):
        raise SyntaxError_(
            "a definition needs `=` or `>` right after the head", items[1].span
        )

    macro = make_source(items[1], scope)
    if items[2].text == "=":
        macro.options.append(items[3:])
    else:
        macro.attribute_lists.append(items[3:])
    return macro


def _add_option(
    current: MacroSource | None, marker: str, closed: bool, line: Line
) -> None:
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


def _parse_nested_scope(
    line: Line, marker: str, parent: Scope, factory: ProduceCallFactory
) -> None:
    """Read a `t Name ( … )` or `p Prefix ( … )` line and its contents.

    A prefix hands its names up to the parent once its own lines are read; a
    target keeps them. The name and the group may be written as two items or
    glued into one, so `p Util_ ( … )` and `p Util_( … )` are the same line.
    """
    name, body = _scope_head(line, marker)
    span = Span.between(line.items[0].span, body.span)

    if marker == "t":
        target = TargetScope(span=span, name=name, parent=parent)
        _parse_lines(body.lines, target, factory)
        parent.add_target(target)
    else:
        scope = Scope(span=span, name=name, parent=parent)
        _parse_lines(body.lines, scope, factory)
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
