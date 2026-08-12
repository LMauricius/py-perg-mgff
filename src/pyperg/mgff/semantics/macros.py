"""Macro definitions: a shape, and what a call of it produces.

A definition is two callables and nothing else. Its **shape** says which calls
it answers to and reads what such a call carries; its **produce_call** turns
that into whatever the caller is generating — a rule tree, a pattern string, a
line of code. The dictionary the shape extracts is handed over as keyword
arguments, so a definition is written with the parameters its shape names:

    MacroDefinition(shape=shapes.REPETITION, produce_call=_repetition)

    def _repetition(body: Rule, marker: str) -> Rule: ...

Anything else a generator needs — the alternatives of a `d` line, an attribute
list, a name — lives in the callable itself, which is normally a closure a
factory built. That is why a definition needs no subclasses, and why the two
fields below are the whole of it.

**ScopeLookupPoint** is not a definition but a place in the order: it says "consult the
grammar's own definitions here". Precedence belongs to the ordered list of
macros rather than to the scope chain — a character set of several parts
outranks a definition however deeply nested it is — so the list names the two
points at which a scope is asked, and the definition found there brings its own
shape to read the call with.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from .shapes import MacroShape

#: Turns what a call carries into whatever the caller is generating.
#:
#: Called as `produce_call(context, **extracted)`: a `CallContext` first, then
#: the shape's dictionary as keyword arguments, so the function is written with
#: the parameters its shape names. Returning None **declines** the call, and the
#: order moves on to the next macro — which is how `9-0`, matching the shape of a
#: character set but naming no valid one, goes on to be read as a name.
#:
#: The return type is `object` rather than a node: what a call produces is the
#: caller's business, and a rule tree is only the most common answer.
ProduceCall = Callable[..., object]


@dataclass(frozen=True, slots=True)
class MacroDefinition:
    """A macro: the calls it answers to, and what such a call produces."""

    shape: MacroShape
    produce_call: ProduceCall


@dataclass(frozen=True, slots=True)
class ScopeLookupPoint:
    """A place in the order where the grammar's own definitions are consulted.

    `shape` is only a filter on the item — a name carrying arguments, or one
    carrying none — since which definitions exist is a question for the scope.
    """

    shape: MacroShape


#: One entry of the ordered list a call is resolved against.
Macro = MacroDefinition | ScopeLookupPoint
