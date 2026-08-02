"""The Part 2 structures: scopes, targets and the definitions they hold.

A scope holds the macros defined in it, the prefix scopes and the targets nested
in it, and a link to its parent. The whole file is a scope too; it simply has no
parent and no closing `)`.

A `d` line is read into a **`MacroSource`**: the head, the alternatives and the
attribute lines, exactly as they were written. The parser hands each source to
the factory it was given, and files the resulting **`MacroDefinition`** here. The
source is kept alongside, since a factory reading one definition may need to see
another as it was written — an attribute list naming another attribute list, for
one.

Definitions are indexed by **signature**, which `mgff.cst` builds: the head's
text with every group replaced by an empty pair of parentheses, so `sep(R)by(S)`
is filed under `sep()by()` and `Digit` under `Digit`. A call carries the same
skeleton as the head it calls, so a call is found by its own signature. The
index is exactly the shapes whose pattern is one fixed name; the shapes
recognised by a pattern proper are in the ordered list of macros, not here.

A `p Prefix ( … )` scope hands its names up: once parsed, every macro and
subscope of it is registered in the parent as well, under `Prefix` + its name.
The entries are the very same objects, and a source always remembers the scope it
was *defined* in, never the one that absorbed it. Nested prefixes concatenate,
since a scope is absorbed only after it has absorbed its own children.

A `t Name ( … )` target keeps its macros to itself: which target may call
another's macros is a decision of the generator, not of MGFF.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ...diagnostics.errors import SemanticError
from ...diagnostics.span import Span
from ..lexing.cst import Group, Item, signature_of
from .macros import MacroDefinition

__all__ = [
    "MacroDefinition",
    "MacroSource",
    "Scope",
    "Target",
    "make_source",
    "signature_of",
]


@dataclass(slots=True)
class MacroSource:
    """A `d Head = Body` line as it was written, for the factory to read.

    `options` are the alternatives, in the order they were written; the first is
    the body of the `d` line itself. `choice_symbol` is `/` or `|`, or None while
    the macro has fewer than two options. `attribute_lists` holds the items of
    each `>` line unread — what an attribute means is Part 3.

    A macro written `d Head > Attributes`, separated by `>` rather than `=`, has
    no options at all. It matches nothing on its own and exists for the
    attributes it carries, which is how a named list of attributes is written.
    """

    span: Span
    head: Item
    name: str  # the head's text without the groups, e.g. `sepby`
    signature: str  # the index key, e.g. `sep()by()`
    scope: Scope  # where it was defined, even when absorbed by a prefix
    parameters: list[str] = field(default_factory=list)
    options: list[list[Item]] = field(default_factory=list)
    attribute_lists: list[list[Item]] = field(default_factory=list)
    choice_symbol: str | None = None

    @property
    def attributes(self) -> list[Item]:
        """Every attribute of the macro; the `>` lines accumulate."""
        return [item for line in self.attribute_lists for item in line]

    @property
    def matches_nothing(self) -> bool:
        """Whether the macro has no options, so it only carries attributes."""
        return not self.options


@dataclass(slots=True)
class Scope:
    """A region holding macros, prefix scopes and targets.

    The file scope has no parent and an empty name. A prefix scope is named by the
    literal text it prepends; a target by the phase it generates.
    """

    span: Span
    name: str = ""
    parent: Scope | None = None
    #: The definitions filed here, and the lines they were read from, under the
    #: same keys. A prefix scope's names appear in both, behind the prefix.
    macros: dict[str, MacroDefinition] = field(default_factory=dict)
    sources: dict[str, MacroSource] = field(default_factory=dict)
    subscopes: dict[str, Scope] = field(default_factory=dict)
    targets: dict[str, Target] = field(default_factory=dict)

    # -- construction ------------------------------------------------------

    def reserve(self, source: MacroSource) -> None:
        """Claim a name for a macro being read, before its definition is built.

        The alternatives of a `d` line arrive one line at a time, so a name is
        taken as soon as it is written and filled in once the macro is complete.
        """
        self._claim(source.signature, source.span, "macro")
        self.sources[source.signature] = source

    def define(self, source: MacroSource, definition: MacroDefinition) -> None:
        """File the definition built from a source this scope has reserved."""
        self.macros[source.signature] = definition

    def add_subscope(self, scope: Scope) -> None:
        """Register a prefix scope nested directly in this one."""
        self._claim(scope.name, scope.span, "prefix", among=self.subscopes)
        self.subscopes[scope.name] = scope

    def add_target(self, target: Target) -> None:
        """Register a target nested directly in this one."""
        self._claim(target.name, target.span, "target", among=self.targets)
        self.targets[target.name] = target

    def absorb(self, child: Scope) -> None:
        """Re-register a prefix scope's names here, each behind its prefix.

        Runs after the child is fully parsed, so the child has already absorbed
        its own children and one pass suffices for any depth of nesting.
        """
        prefix = child.name
        for signature, source in child.sources.items():
            self._claim(prefix + signature, source.span, "macro")
            self.sources[prefix + signature] = source
            if signature in child.macros:
                self.macros[prefix + signature] = child.macros[signature]
        for name, scope in child.subscopes.items():
            self._claim(prefix + name, scope.span, "prefix", among=self.subscopes)
            self.subscopes[prefix + name] = scope

    def _claim(
        self,
        key: str,
        span: Span,
        kind: str,
        among: dict[str, Scope] | dict[str, Target] | None = None,
    ) -> None:
        """Reject a name already taken in this scope, pointing at the newcomer."""
        taken = self.sources if among is None else among
        if key in taken:
            raise SemanticError(
                f"{kind} {key!r} is already defined in this scope", span
            )

    # -- lookup ------------------------------------------------------------

    def lookup(self, signature: str) -> MacroDefinition | None:
        """Find a definition by signature, this scope first, then the enclosing ones.

        A target is an ordinary link in the chain going outwards: a macro defined
        outside every target and prefix is visible to all of them.
        """
        scope: Scope | None = self
        while scope is not None:
            if signature in scope.macros:
                return scope.macros[signature]
            scope = scope.parent
        return None

    def lookup_source(self, signature: str) -> MacroSource | None:
        """Find the line a definition was read from, the same way."""
        scope: Scope | None = self
        while scope is not None:
            if signature in scope.sources:
                return scope.sources[signature]
            scope = scope.parent
        return None

    @property
    def qualified_name(self) -> str:
        """The scope's name with the names of its enclosing scopes in front."""
        names = []
        scope: Scope | None = self
        while scope is not None:
            names.append(scope.name)
            scope = scope.parent
        return "".join(reversed(names))


@dataclass(slots=True)
class Target(Scope):
    """One generation phase, typically `Lex` for tokens and `Parse` for grammar."""


def make_source(head: Item, scope: Scope) -> MacroSource:
    """Build an empty source from its head item, reading its parameter names.

    The text outside the head's groups is the name; each group declares one
    parameter, named by the single item inside it.
    """
    return MacroSource(
        span=head.span,
        head=head,
        name=head.text,
        signature=signature_of(head),
        scope=scope,
        parameters=[_parameter_name(group) for group in head.groups],
    )


def _parameter_name(group: Group) -> str:
    """The name declared by one slot of a head: the single item inside it."""
    items = [item for line in group.lines for item in line.items]
    if len(items) != 1 or not items[0].is_bare_text:
        raise SemanticError("a parameter slot holds one plain name", group.span)
    return items[0].text
