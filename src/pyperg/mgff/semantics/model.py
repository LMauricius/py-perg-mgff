"""The resolved grammar handed to a generator.

This is the boundary between the front end and the backends: everything MGFF
defines has been read and resolved, and nothing here refers to the concrete
syntax any more.

A production's alternatives are **rule trees**, whose node kinds are described
in `nodes`. Only `Reference` still names something; every other node is
self-contained, and a `MacroCall` keeps the item it was written as, for whoever
defined the macro that built it.

This module is one **factory**: it says what a call produces, namely a node of a
rule tree, and the parser does the rest. Reading an item is the same walk every
time — its signature is matched against the macros in force, in order, and the
first definition that does not decline produces the node. A definition carrying
parameters expands in place, since a mixfix macro has no body of its own to
point at, while an argument-less one becomes a reference, so a recursive or
mutually recursive grammar resolves without looping.

Which macros are in force is fixed before parsing starts: the built-ins of
`builtins`, plus whatever the chosen backend adds.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ...diagnostics.errors import SemanticError
from ...diagnostics.span import Span
from ..grammar.expand import expand
from ..grammar.macros import Macro, ProduceCall, Scoped
from ..grammar.parser import parse
from ..grammar.scope import MacroSource, Scope, Target as ScopeTarget, signature_of
from ..lexing.cst import File, Group, Item, group_items, render_item
from .builtins import collect_attributes, rule_tree_macros

# The node kinds are re-exported: a backend reads the model through this module.
from .nodes import (
    Choice,
    MacroCall,
    Node,
    Reference,
    Repetition,
    Sequence,
)  # noqa: F401

#: Targets known to match textual characters throughout, so a rule of theirs is
#: never anything but characters. Other targets may still spell a terminal as a
#: character — Appendix A's `Parse` writes `\( Expr \)` — so character sets are
#: read everywhere; a name that resolves always outranks a single-part set, and
#: a misspelling is still an unknown name rather than a silent character.
CHARACTER_TARGETS: frozenset[str] = frozenset({"Lex"})

#: How deep a mixfix macro may expand before it is called recursive.
MAX_EXPANSION_DEPTH = 64


# -- the model -------------------------------------------------------------


@dataclass(slots=True)
class Production:
    """A macro a target treats as a matching rule."""

    name: str
    alternatives: list[Node] = field(default_factory=list)
    choice_symbol: str | None = (
        None  # `/` order-based, `|` length-based, None if single
    )
    attributes: dict[str, list[str]] = field(default_factory=dict)
    span: Span | None = None
    #: The target the macro was written in, `""` when it is shared by all of
    #: them. A production reached across a target boundary keeps its origin, so
    #: a backend can tell a token apart from a rule of its own phase.
    origin: str = ""

    @property
    def rule(self) -> Node:
        """The production's alternatives as one node."""
        if len(self.alternatives) == 1:
            return self.alternatives[0]
        return Choice(list(self.alternatives), self.choice_symbol or "/")


@dataclass(slots=True)
class Target:
    """One generation phase, typically `Lex` for tokens and `Parse` for grammar."""

    name: str
    productions: dict[str, Production] = field(default_factory=dict)
    #: Whether the target matches characters throughout, rather than only where
    #: a terminal is spelled as one. `Lex` does; `Parse` matches tokens.
    matches_characters: bool = False


@dataclass(slots=True)
class GrammarModel:
    """The whole resolved grammar."""

    name: str
    targets: list[Target] = field(default_factory=list)
    #: File-scope attribute-only macros, by name, e.g. `Language` -> its attributes.
    metadata: dict[str, dict[str, list[str]]] = field(default_factory=dict)

    def target(self, name: str) -> Target | None:
        """One target by name, or None when the grammar has no such phase."""
        return next((t for t in self.targets if t.name == name), None)


# -- resolution ------------------------------------------------------------


def resolve(
    file: File, name: str = "grammar", macros: list[Macro] | None = None
) -> GrammarModel:
    """Read a lexed file as the model a rule-tree backend generates from.

    Parses the file with the rule-tree factory, then collects the productions per
    target. `name` names the grammar, normally the source file it came from.
    `macros` are the definitions in force, the built-in ones when a caller names
    no others.
    """
    trees = RuleTrees(macros if macros is not None else rule_tree_macros())
    grammar = parse(file, trees.factory)

    model = GrammarModel(name=name)
    # Earlier targets stay visible to later ones: MGFF leaves the decision to
    # the generator, and a `Parse` naming the tokens of a `Lex` is the usual
    # arrangement — Appendix A writes `d Factor = Number / Ident / \( Expr \)`.
    earlier: list[ScopeTarget] = []
    for target_name, scope_target in grammar.targets.items():
        model.targets.append(trees.resolve_target(target_name, scope_target, earlier))
        earlier.append(scope_target)
    model.metadata = _resolve_metadata(grammar)
    return model


def _resolve_metadata(grammar: Scope) -> dict[str, dict[str, list[str]]]:
    """The attribute-only macros defined outside every target.

    These carry no rule and describe the grammar itself, which is where a
    backend reads settings such as the generated language's name.
    """
    return {
        source.name: collect_attributes(source)
        for source in grammar.sources.values()
        if source.matches_nothing
    }


def _target_name(source: MacroSource) -> str:
    """The name of the target a macro was written in, `""` when it is shared."""
    defining = _defining_target(source)
    return defining.name if defining is not None else ""


def _defining_target(source: MacroSource) -> ScopeTarget | None:
    """The target a macro was written in, or None when it is shared by all."""
    scope: Scope | None = source.scope
    while scope is not None:
        if isinstance(scope, ScopeTarget):
            return scope
        scope = scope.parent
    return None


class RuleTrees:
    """The factory building rule trees, and the resolver reading items for it.

    A definition's `produce_call` is built once, at parse time, and called once
    per use — possibly under several targets, since a macro reached from two
    targets is resolved once for each. What differs between those uses is the
    production table it registers in and the scope the call was written in, so
    both are held here, in `current`, rather than captured per definition.
    """

    def __init__(self, macros: list[Macro]) -> None:
        self.macros = macros
        self.current: _Resolver | None = None

    # -- the factory -------------------------------------------------------

    def factory(self, source: MacroSource) -> ProduceCall:
        """What a call of one `d` definition produces: a node of a rule tree."""

        def produce_call(**arguments: object) -> Node:
            assert self.current is not None  # only ever called while resolving
            return self.current.call(source, arguments)

        return produce_call

    # -- driving -----------------------------------------------------------

    def resolve_target(
        self, name: str, scope_target: ScopeTarget, earlier: list[ScopeTarget]
    ) -> Target:
        """Resolve every production a target owns or reaches."""
        target = Target(name=name, matches_characters=name in CHARACTER_TARGETS)
        resolver = _Resolver(self, target, earlier)
        previous, self.current = self.current, resolver
        try:
            # Seed with the macros written directly in the target; references
            # then pull in whatever else they reach, including macros shared
            # outside it.
            for source in list(scope_target.sources.values()):
                if not source.matches_nothing:
                    resolver.require(source)
            resolver.run()
        finally:
            self.current = previous
        return target


class _Resolver:
    """Builds one target's production table, following references as it goes."""

    def __init__(
        self, trees: RuleTrees, target: Target, earlier: list[ScopeTarget]
    ) -> None:
        self.trees = trees
        self.target = target
        self.earlier = earlier
        self.pending: list[tuple[str, MacroSource]] = []
        # Which name each macro was filed under, so a second reference to the
        # same macro reuses it instead of renaming it.
        self.names: dict[int, str] = {}
        # Where the item being read was written, and how deep the expansion of
        # mixfix calls has gone. A definition's `produce_call` reads both.
        self.scope: Scope | None = None
        self.depth = 0

    # -- driving -----------------------------------------------------------

    def require(self, source: MacroSource) -> str:
        """Register a macro as a production of this target and return its name."""
        if id(source) in self.names:
            return self.names[id(source)]
        name = self.production_name(source)
        self.names[id(source)] = name
        # Reserve the name before resolving, so a self-reference finds it.
        self.target.productions[name] = Production(
            name=name, span=source.span, origin=_target_name(source)
        )
        self.pending.append((name, source))
        return name

    def run(self) -> None:
        """Resolve every registered macro, and everything they reach."""
        while self.pending:
            name, source = self.pending.pop(0)
            production = self.target.productions[name]
            production.choice_symbol = source.choice_symbol
            production.attributes = collect_attributes(source)
            production.alternatives = [
                self.sequence(option, source.scope, depth=0)
                for option in source.options
            ]

    def production_name(self, source: MacroSource) -> str:
        """A macro's name, relative to the target it was defined in.

        `Lex` calls its own `Int` by that name and so does a later target, since
        a name that resolves locally is never the one reached across a target
        boundary. A prefix scope contributes `Util_pair`, and a macro shared
        outside every target keeps its bare name. Only a genuine clash — the
        same name defined in two targets and both reached here — falls back to
        qualifying it.
        """
        defining = _defining_target(source)
        own = defining.qualified_name if defining is not None else ""
        qualified = source.scope.qualified_name
        name = qualified[len(own) :] + source.signature
        if name not in self.target.productions:
            return name
        return qualified + source.signature

    # -- item to node ------------------------------------------------------

    def sequence(self, items: list[Item], scope: Scope, depth: int) -> Node:
        """A run of items as one node, unwrapped when there is only one."""
        nodes = [self.node(item, scope, depth) for item in items]
        return nodes[0] if len(nodes) == 1 else Sequence(nodes)

    def node(self, item: Item, scope: Scope, depth: int) -> Node:
        """One item as a node, read through the macros in force.

        They are tried in order, and the first definition that does not decline
        wins. An item every one of them declines calls nothing that is in force
        here, which is what an unknown name is.
        """
        signature = signature_of(item)
        for macro in self.trees.macros:
            match = macro.shape.match(signature)
            if match is None:
                continue
            # `Scoped` is a place in the order rather than a macro: the grammar's
            # own definitions are consulted here, and the one found brings the
            # shape that reads the call's arguments.
            definition = macro
            if isinstance(macro, Scoped):
                found = self.lookup(signature, scope)
                if found is None:
                    continue
                definition = found
            arguments = definition.shape.extract_args(item, match)
            node = self.produce(definition.produce_call, arguments, scope, depth, item)
            if node is not None:
                return node
        raise SemanticError(f"unknown name {render_item(item)!r}", item.span)

    def produce(
        self,
        produce_call: ProduceCall,
        arguments: dict[str, object],
        scope: Scope,
        depth: int,
        item: Item,
    ) -> Node | None:
        """Call a definition, with the rules among its arguments read first.

        A group is a rule, so it is resolved before the call is made and a macro
        such as `( R )+` never touches the resolver. Anything else is passed on
        as it was extracted — the items filling a mixfix macro's slot, say, which
        are substituted into its body rather than read where they stand.
        """
        read = {
            name: self.produced(value, scope, depth)
            for name, value in arguments.items()
        }
        previous = (self.scope, self.depth)
        self.scope, self.depth = scope, depth
        try:
            return produce_call(**read)  # type: ignore[return-value]
        finally:
            self.scope, self.depth = previous

    def produced(self, value: object, scope: Scope, depth: int) -> object:
        """A group as the rule it holds; anything else unchanged."""
        if isinstance(value, Group):
            return self.sequence(group_items(value), scope, depth)
        if isinstance(value, list) and all(isinstance(one, Group) for one in value):
            return [self.sequence(group_items(one), scope, depth) for one in value]
        return value

    # -- name lookup -------------------------------------------------------

    def lookup(self, signature: str, scope: Scope):
        """Find a definition from a scope, then in the targets resolved before this one.

        A target keeps its macros to itself as far as MGFF is concerned; letting
        a later target see an earlier one is this generator's policy.
        """
        definition = scope.lookup(signature)
        if definition is not None:
            return definition
        for previous in reversed(self.earlier):
            if signature in previous.macros:
                return previous.macros[signature]
        return None

    # -- what a `d` definition produces ------------------------------------

    def call(self, source: MacroSource, arguments: dict[str, object]) -> Node:
        """A call of one of the grammar's own definitions.

        An argument-less one is linked rather than expanded, so a recursive
        grammar terminates. One carrying parameters has no body to point at, so
        its call is substituted; the depth limit is what stops a mixfix macro
        that expands into itself.
        """
        scope, depth = self.scope, self.depth
        assert scope is not None
        if source.matches_nothing:
            raise SemanticError(
                f"{source.name!r} is a list of attributes and matches nothing",
                source.span,
            )
        if not source.parameters:
            return Reference(self.require(source))

        if depth >= MAX_EXPANSION_DEPTH:
            raise SemanticError(
                f"expansion of {source.name!r} is too deep; "
                "a macro with parameters may not expand into itself",
                source.span,
            )
        # The expansion is read in the *calling* scope: the arguments were
        # written there, and the body's own names resolve outward all the same.
        bindings = {name: value for name, value in arguments.items()}
        nodes = [
            self.sequence(option, scope, depth + 1)
            for option in expand(source.options, bindings)  # type: ignore[arg-type]
        ]
        if len(nodes) == 1:
            return nodes[0]
        return Choice(nodes, source.choice_symbol or "/")
