"""What a macro is told about the call it is answering.

Every `produce_call` takes a `CallContext` as its first argument, whatever its
shape extracted. Most macros ignore it: `( R )+` repeats its body wherever it was
written. The ones that do not are the grammar's own definitions, which need to
know where the call stands in order to resolve the names around it.

The context is passed rather than held: a definition is built once, when the file
is parsed, but called once per use and possibly under several targets. Nothing
about a particular call is therefore captured in the definition.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ..grammar.scope import MacroSource, Scope


class Resolver(Protocol):
    """The part of the resolver a grammar's own definition calls back into."""

    def call_defined(
        self, source: MacroSource, context: CallContext, arguments: dict[str, object]
    ) -> object:
        """Produce the node a call of one of the grammar's definitions stands for."""


@dataclass(frozen=True, slots=True)
class CallContext:
    """Where a call was written, and how far its expansion has gone."""

    #: The scope the item was written in, which is where its names resolve from.
    scope: Scope
    #: How many mixfix expansions deep the call is. A macro carrying parameters
    #: is substituted rather than linked, so this is what bounds the recursion.
    depth: int
    #: The resolver reading the target this call belongs to.
    resolver: Resolver
