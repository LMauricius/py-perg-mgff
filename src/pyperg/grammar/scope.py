"""The Part 2 structures: scopes, targets and macros.

A scope holds the macros defined in it, the prefix scopes and the targets nested
in it, and a link to its parent. The whole file is a scope too; it simply has no
parent and no closing `)`.

Names are keyed by **signature**: the head's text with every group replaced by an
empty pair of parentheses, so `sep(R)by(S)` is keyed `sep()by()` and `Digit` is
keyed `Digit`. A call carries the same skeleton as the head it calls, so a call is
looked up by its own signature without any further bookkeeping.

A `p Prefix ( … )` scope hands its names up: once parsed, every macro and
subscope of it is registered in the parent as well, under `Prefix` + its name.
The entries are the very same objects, and a macro always remembers the scope it
was *defined* in, never the one that absorbed it. Nested prefixes concatenate,
since a scope is absorbed only after it has absorbed its own children.

A `t Name ( … )` target keeps its macros to itself: which target may call
another's macros is a decision of the generator, not of MGFF.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..diagnostics.errors import SemanticError
from ..diagnostics.span import Span
from ..mgff.cst import Group, Item, Text


def signature_of(item: Item) -> str:
    """The lookup key of a head or a call: its text with the groups emptied.

    `sep(R)by(S)` and `sep(Ident = Expr)by(,)` both give `sep()by()`, so a call
    finds its macro by shape alone.
    """
    out: list[str] = []
    for part in item.parts:
        out.append(part.value if isinstance(part, Text) else "()")
    return "".join(out)


@dataclass(slots=True)
class Macro:
    """A macro definition: `d Head = Body`, with its later lines folded in.

    `options` are the alternatives, in the order they were written; the first is
    the body of the `d` line itself. `choice_symbol` is `/` or `|`, or None while
    the macro has a single option. `attribute_lists` holds the items of each `>`
    line unread — what an attribute means is Part 3.
    """

    span: Span
    head: Item
    name: str  # the head's text without the groups, e.g. `sepby`
    signature: str  # the lookup key, e.g. `sep()by()`
    scope: Scope  # where it was defined, even when absorbed by a prefix
    parameters: list[str] = field(default_factory=list)
    options: list[list[Item]] = field(default_factory=list)
    attribute_lists: list[list[Item]] = field(default_factory=list)
    choice_symbol: str | None = None

    @property
    def attributes(self) -> list[Item]:
        """Every attribute of the macro; the `>` lines accumulate."""
        return [item for line in self.attribute_lists for item in line]


@dataclass(slots=True)
class Scope:
    """A region holding macros, prefix scopes and targets.

    The file scope has no parent and an empty name. A prefix scope is named by the
    literal text it prepends; a target by the phase it generates.
    """

    span: Span
    name: str = ""
    parent: Scope | None = None
    macros: dict[str, Macro] = field(default_factory=dict)
    subscopes: dict[str, Scope] = field(default_factory=dict)
    targets: dict[str, Target] = field(default_factory=dict)

    # -- construction ------------------------------------------------------

    def define(self, macro: Macro) -> None:
        """Register a macro defined directly in this scope."""
        self._claim(macro.signature, macro.span, "macro")
        self.macros[macro.signature] = macro

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
        for signature, macro in child.macros.items():
            self._claim(prefix + signature, macro.span, "macro")
            self.macros[prefix + signature] = macro
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
        taken = self.macros if among is None else among
        if key in taken:
            raise SemanticError(f"{kind} {key!r} is already defined in this scope", span)

    # -- lookup ------------------------------------------------------------

    def lookup(self, signature: str) -> Macro | None:
        """Find a macro by signature, this scope first, then the enclosing ones.

        A target is an ordinary link in the chain going outwards: a macro defined
        outside every target and prefix is visible to all of them.
        """
        scope: Scope | None = self
        while scope is not None:
            if signature in scope.macros:
                return scope.macros[signature]
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


def make_macro(head: Item, scope: Scope) -> Macro:
    """Build an empty macro from its head item, reading its parameter names.

    The text outside the head's groups is the name; each group declares one
    parameter, named by the single item inside it.
    """
    return Macro(
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
