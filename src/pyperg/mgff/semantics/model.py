"""The resolved grammar handed to a generator.

This is the boundary between the front end and the backends: everything MGFF
defines has been read and resolved, and nothing here refers to the concrete
syntax any more.

A production's alternatives are **rule trees**, whose node kinds live
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

Which macros are in force is fixed before parsing starts, and is handed to
`resolve` rather than decided here: the common vocabulary of `mgff.common`, plus
whatever the chosen backend adds to it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import cast

from ...diagnostics.errors import SemanticError
from ...diagnostics.span import Span
from ..grammar.expand import expand
from ..grammar.macros import Macro, ProduceCall, Scoped
from ..grammar.parser import parse
from ..grammar.scope import MacroSource, Scope, TargetScope, signature_of
from ..lexing.cst import File, Group, Item, group_items, render_item
from .attributes import collect_attributes
from .context import CallContext
from ..common.rules import Choice, Rule, Reference, Sequence

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
    alternatives: list[Rule] = field(default_factory=list)
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
    def rule(self) -> Rule:
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
    #: The macros written outside every target, resolved as a target of their
    #: own. A grammar generating one thing needs no phases at all, and a backend
    #: such as the regular-expression one reads only this.
    globals: Target = field(default_factory=lambda: Target(name=""))
    #: File-scope attribute-only macros, by name, e.g. `Language` -> its attributes.
    metadata: dict[str, dict[str, list[str]]] = field(default_factory=dict)

    def target(self, name: str) -> Target | None:
        """One target by name, or None when the grammar has no such phase."""
        return next((t for t in self.targets if t.name == name), None)


# -- resolution ------------------------------------------------------------


def resolve(file: File, name: str, macros: list[Macro]) -> GrammarModel:
    """Read a lexed file as the model a rule-tree backend generates from.

    Parses the file with the rule-tree factory, then collects the productions per
    target. `name` names the grammar, normally the source file it came from.

    `macros` are the definitions in force, and they are asked for rather than
    assumed: nothing in MGFF says what `( R )+` means, so the vocabulary is the
    generator's to choose. `mgff.common.rule_tree_macros` builds the usual one.
    """
    grammar = parse(file, defined_macro_factory)

    model = GrammarModel(name=name)
    # Earlier targets stay visible to later ones: MGFF leaves the decision to
    # the generator, and a `Parse` naming the tokens of a `Lex` is the usual
    # arrangement — Appendix A writes `d Factor = Number / Ident / \( Expr \)`.
    earlier: list[TargetScope] = []
    for target_name, scope_target in grammar.targets.items():
        model.targets.append(
            resolve_target(macros, target_name, scope_target, earlier)
        )
        earlier.append(scope_target)
    # The file scope resolves on its own, and after the targets: its macros see
    # nothing but each other, since a scope is searched outwards only.
    model.globals = resolve_target(macros, "", grammar, [])
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


def _defining_target(source: MacroSource) -> TargetScope | None:
    """The target a macro was written in, or None when it is shared by all."""
    scope: Scope | None = source.scope
    while scope is not None:
        if isinstance(scope, TargetScope):
            return scope
        scope = scope.parent
    return None


def defined_macro_factory(source: MacroSource) -> ProduceCall:
    """What a call of one of the grammar's own `d` definitions produces.

    Built while the file is parsed, long before any resolver exists, so the
    resolver to use arrives with the call rather than being captured here.
    """

    def produce_call(context: CallContext, **arguments: object) -> object:
        return context.resolver.call_defined(source, context, arguments)

    return produce_call


def resolve_target(
    macros: list[Macro],
    name: str,
    scope_target: Scope,
    earlier: list[TargetScope],
) -> Target:
    """Resolve every production one target owns or reaches.

    The file scope is resolved through this too, under the empty name, which is
    what a grammar written without targets amounts to.
    """
    target = Target(name=name, matches_characters=name in CHARACTER_TARGETS)
    resolver = _Resolver(macros, target, earlier)
    # Seed with the macros written directly in the target; references then pull
    # in whatever else they reach, including macros shared outside it. A macro
    # carrying parameters is not seeded: its body is written in terms of names
    # only a call supplies, so it means nothing until one is made.
    for source in list(scope_target.sources.values()):
        if not source.matches_nothing and not source.parameters:
            resolver.require(source)
    resolver.run()
    return target


class _Resolver:
    """Builds one target's production table, following references as it goes."""

    def __init__(
        self, macros: list[Macro], target: Target, earlier: list[TargetScope]
    ) -> None:
        self.macros = macros
        self.target = target
        self.earlier = earlier
        self.pending: list[tuple[str, MacroSource]] = []
        # Which name each macro was filed under, so a second reference to the
        # same macro reuses it instead of renaming it. Sources compare by
        # identity, so the same `d` line is the same key however it is reached.
        self.names: dict[MacroSource, str] = {}

    # -- driving -----------------------------------------------------------

    def require(self, source: MacroSource) -> str:
        """Register a macro as a production of this target and return its name."""
        if source in self.names:
            return self.names[source]
        name = self.production_name(source)
        self.names[source] = name
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

    def sequence(self, items: list[Item], scope: Scope, depth: int) -> Rule:
        """A run of items as one node, unwrapped when there is only one."""
        nodes = [self.node(item, scope, depth) for item in items]
        return nodes[0] if len(nodes) == 1 else Sequence(nodes)

    def node(self, item: Item, scope: Scope, depth: int) -> Rule:
        """One item as a node, read through the macros in force.

        They are tried in order, and the first definition that does not decline
        wins. An item every one of them declines calls nothing that is in force
        here, which is what an unknown name is.
        """
        signature = signature_of(item)
        for macro in self.macros:
            # `Scoped` is a place in the order rather than a macro: its shape
            # only filters the item, and the grammar's own definitions are
            # consulted there.
            selected = macro.shape.match(signature)
            if selected is None:
                continue
            definition = self.lookup(signature, scope) if isinstance(macro, Scoped) else macro
            if definition is None:
                continue
            # `selected` belongs to the pattern that chose the macro, which for a
            # `Scoped` is the filter rather than the definition's own pattern.
            # The two differ for a prefix scope — `Util_pair` is found under that
            # key while the definition's pattern is the `pair` it was written as
            # — so a definition reached by name reads the item alone and never
            # touches the match.
            arguments = definition.shape.extract_args(item, selected)
            node = self.produce(definition.produce_call, arguments, scope, depth)
            if node is not None:
                return node
        raise SemanticError(f"unknown name {render_item(item)!r}", item.span)

    def produce(
        self,
        produce_call: ProduceCall,
        arguments: dict[str, object],
        scope: Scope,
        depth: int,
    ) -> Rule | None:
        """Call a definition, with the rules among its arguments read first.

        A group is a rule, so it is resolved before the call is made and a macro
        such as `( R )+` never touches the resolver. Anything else is passed on
        as it was extracted — the items filling a mixfix macro's slot, say, which
        are substituted into its body rather than read where they stand.

        A definition returning None declines the call, and the order moves on to
        the next macro: `9-0` is no character set, so it goes on to be read as a
        name and reported as an unknown one.
        """
        read = {
            name: self.produced(value, scope, depth)
            for name, value in arguments.items()
        }
        context = CallContext(scope=scope, depth=depth, resolver=self)
        return cast("Rule | None", produce_call(context, **read))

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

    def call_defined(
        self, source: MacroSource, context: CallContext, arguments: dict[str, object]
    ) -> Rule:
        """A call of one of the grammar's own definitions.

        An argument-less one is linked rather than expanded, so a recursive
        grammar terminates. One carrying parameters has no body to point at, so
        its call is substituted; the depth limit is what stops a mixfix macro
        that expands into itself.
        """
        scope, depth = context.scope, context.depth
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
            for option in expand(source.options, cast("dict[str, list[Item]]", bindings))
        ]
        if len(nodes) == 1:
            return nodes[0]
        return Choice(nodes, source.choice_symbol or "/")
