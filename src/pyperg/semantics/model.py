"""The resolved grammar handed to a generator.

This is the boundary between the front end and the backends: everything MGFF
defines has been read and resolved, and nothing here refers to the concrete
syntax any more.

A production's alternatives are **rule trees** built from five node kinds. Only
`Reference` still names something; every other node is self-contained.

    Sequence     items matched one after another
    Repetition   a body matched a number of times
    Choice       one of several options, order- or length-based
    Reference    another production of the same target
    Chars        one character from a character set

Calls carrying arguments are expanded here, since a mixfix macro has no body of
its own to point at. Argument-less calls stay as references, so a recursive or
mutually recursive grammar resolves without looping.

A macro reached from more than one target is resolved once per target, because
whether character sets apply is a property of the target, not of the macro.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..diagnostics.errors import SemanticError
from ..diagnostics.span import Span
from ..grammar.expand import arguments_of, expand_call
from ..grammar.scope import Macro, Scope, Target as ScopeTarget, signature_of
from ..mgff.cst import Group, Item, render_item
from .builtins import REPETITION_MARKERS, collect_attributes
from .charset import CharacterSet, parse_character_set
from .shapes import Shape, choice_symbol, classify, group_items, is_repetition

#: Targets known to match textual characters throughout, so a rule of theirs is
#: never anything but characters. Other targets may still spell a terminal as a
#: character — Appendix A's `Parse` writes `\( Expr \)` — so character sets are
#: read everywhere; a name that resolves always outranks a single-part set, and
#: a misspelling is still an unknown name rather than a silent character.
CHARACTER_TARGETS: frozenset[str] = frozenset({"Lex"})

#: How deep a mixfix macro may expand before it is called recursive.
MAX_EXPANSION_DEPTH = 64


# -- the rule tree ---------------------------------------------------------


@dataclass(slots=True)
class Sequence:
    """Items matched one after another. An empty sequence matches nothing."""

    items: list["Node"] = field(default_factory=list)


@dataclass(slots=True)
class Repetition:
    """A body matched between `minimum` and `maximum` times, `None` for no limit."""

    body: "Node"
    minimum: int
    maximum: int | None
    marker: str  # `+`, `*` or `?`, kept for round-tripping and messages


@dataclass(slots=True)
class Choice:
    """One of several options.

    `symbol` is `/` when the first option that succeeds wins and `|` when the
    longest match wins.
    """

    options: list["Node"]
    symbol: str


@dataclass(slots=True)
class Reference:
    """A call on another production of the same target.

    `name` is how the production is named inside its target, which is also the
    key it is filed under in `Target.productions`.
    """

    name: str


@dataclass(slots=True)
class Chars:
    """One character from a character set."""

    characters: CharacterSet


Node = Sequence | Repetition | Choice | Reference | Chars


# -- the model -------------------------------------------------------------


@dataclass(slots=True)
class Production:
    """A macro a target treats as a matching rule."""

    name: str
    alternatives: list[Node] = field(default_factory=list)
    choice_symbol: str | None = None  # `/` order-based, `|` length-based, None if single
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


def resolve(grammar: Scope, name: str = "grammar") -> GrammarModel:
    """Turn a parsed grammar into the resolved model.

    Builds the symbol tables, classifies every item by shape, checks that calls
    resolve and that attributes are understood, then collects the productions
    per target. Argument-less calls are *not* expanded here: expansion happens on
    demand, since the call graph may contain cycles.

    `name` names the grammar, normally the source file it came from; the root
    scope does not carry one.
    """
    model = GrammarModel(name=name)
    # Earlier targets stay visible to later ones: MGFF leaves the decision to
    # the generator, and a `Parse` naming the tokens of a `Lex` is the usual
    # arrangement — Appendix A writes `d Factor = Number / Ident / \( Expr \)`.
    earlier: list[ScopeTarget] = []
    for target_name, scope_target in grammar.targets.items():
        model.targets.append(_resolve_target(target_name, scope_target, earlier))
        earlier.append(scope_target)
    model.metadata = _resolve_metadata(grammar)
    return model


def _resolve_metadata(grammar: Scope) -> dict[str, dict[str, list[str]]]:
    """The attribute-only macros defined outside every target.

    These carry no rule and describe the grammar itself, which is where a
    backend reads settings such as the generated language's name.
    """
    return {
        macro.name: collect_attributes(macro)
        for macro in grammar.macros.values()
        if macro.matches_nothing
    }


def _target_name(macro: Macro) -> str:
    """The name of the target a macro was written in, `""` when it is shared."""
    defining = _defining_target(macro)
    return defining.name if defining is not None else ""


def _defining_target(macro: Macro) -> ScopeTarget | None:
    """The target a macro was written in, or None when it is shared by all."""
    scope: Scope | None = macro.scope
    while scope is not None:
        if isinstance(scope, ScopeTarget):
            return scope
        scope = scope.parent
    return None


def _resolve_target(
    name: str, scope_target: ScopeTarget, earlier: list[ScopeTarget]
) -> Target:
    """Resolve every production a target owns or reaches."""
    target = Target(name=name, matches_characters=name in CHARACTER_TARGETS)
    resolver = _Resolver(target, scope_target, earlier)
    # Seed with the macros written directly in the target; references then pull
    # in whatever else they reach, including macros shared outside the target.
    for macro in list(scope_target.macros.values()):
        if not macro.matches_nothing:
            resolver.require(macro)
    resolver.run()
    return target


class _Resolver:
    """Builds one target's production table, following references as it goes."""

    def __init__(
        self, target: Target, scope_target: ScopeTarget, earlier: list[ScopeTarget]
    ) -> None:
        self.target = target
        self.scope_target = scope_target
        self.earlier = earlier
        self.pending: list[tuple[str, Macro]] = []
        # Which name each macro was filed under, so a second reference to the
        # same macro reuses it instead of renaming it.
        self.names: dict[int, str] = {}

    # -- driving -----------------------------------------------------------

    def require(self, macro: Macro) -> str:
        """Register a macro as a production of this target and return its name."""
        if id(macro) in self.names:
            return self.names[id(macro)]
        name = self.production_name(macro)
        self.names[id(macro)] = name
        # Reserve the name before resolving, so a self-reference finds it.
        self.target.productions[name] = Production(
            name=name, span=macro.span, origin=_target_name(macro)
        )
        self.pending.append((name, macro))
        return name

    def run(self) -> None:
        """Resolve every registered macro, and everything they reach."""
        while self.pending:
            name, macro = self.pending.pop(0)
            production = self.target.productions[name]
            production.choice_symbol = macro.choice_symbol
            production.attributes = collect_attributes(macro)
            production.alternatives = [
                self.sequence(option, macro.scope, depth=0) for option in macro.options
            ]

    def production_name(self, macro: Macro) -> str:
        """A macro's name, relative to the target it was defined in.

        `Lex` calls its own `Int` by that name and so does a later target, since
        a name that resolves locally is never the one reached across a target
        boundary. A prefix scope contributes `Util_pair`, and a macro shared
        outside every target keeps its bare name. Only a genuine clash — the
        same name defined in two targets and both reached here — falls back to
        qualifying it.
        """
        defining = _defining_target(macro)
        own = defining.qualified_name if defining is not None else ""
        qualified = macro.scope.qualified_name
        name = qualified[len(own) :] + macro.signature
        if name not in self.target.productions:
            return name
        return qualified + macro.signature

    # -- name lookup -------------------------------------------------------

    def lookup(self, signature: str, scope: Scope) -> Macro | None:
        """Find a macro from a scope, then in the targets resolved before this one.

        A target keeps its macros to itself as far as MGFF is concerned; letting
        a later target see an earlier one is this generator's policy.
        """
        macro = scope.lookup(signature)
        if macro is not None:
            return macro
        for previous in reversed(self.earlier):
            if signature in previous.macros:
                return previous.macros[signature]
        return None

    # -- item to node ------------------------------------------------------

    def sequence(self, items: list[Item], scope: Scope, depth: int) -> Node:
        """A run of items as one node, unwrapped when there is only one."""
        nodes = [self.node(item, scope, depth) for item in items]
        return nodes[0] if len(nodes) == 1 else Sequence(nodes)

    def node(self, item: Item, scope: Scope, depth: int) -> Node:
        """One item as a node, read by its shape."""
        shape = classify(
            item,
            character_sets_allowed=True,
            resolves=lambda text: self.lookup(text, scope) is not None,
        )

        if shape is Shape.SUBGROUP:
            return self.group(item.groups[0], scope, depth)

        if shape is Shape.REPETITION:
            _, marker = is_repetition(item)
            minimum, maximum = REPETITION_MARKERS[marker]
            body = self.group(item.groups[0], scope, depth)
            return Repetition(body, minimum, maximum, marker)

        if shape is Shape.CHOICE:
            symbol = choice_symbol(item) or "/"
            options = [self.group(group, scope, depth) for group in item.groups]
            return Choice(options, symbol)

        if shape is Shape.CHARACTER_SET:
            characters = parse_character_set(item.text)
            assert characters is not None  # the shape was decided by parsing it
            return Chars(characters)

        if shape is Shape.CALL_WITH_ARGUMENTS:
            return self.expanded_call(item, scope, depth)

        return self.reference(item, scope)

    def group(self, group: Group, scope: Scope, depth: int) -> Node:
        """A group's contents as one node; its line breaks are layout only."""
        return self.sequence(group_items(group), scope, depth)

    # -- calls -------------------------------------------------------------

    def reference(self, item: Item, scope: Scope) -> Reference:
        """An argument-less call, linked rather than expanded."""
        macro = self.lookup(signature_of(item), scope)
        if macro is None:
            raise SemanticError(f"unknown name {render_item(item)!r}", item.span)
        if macro.matches_nothing:
            raise SemanticError(
                f"{item.text!r} is a list of attributes and matches nothing", item.span
            )
        return Reference(self.require(macro))

    def expanded_call(self, item: Item, scope: Scope, depth: int) -> Node:
        """A call carrying arguments, expanded in place.

        A mixfix macro has no body to point at, so its call is substituted here.
        The depth limit is what stops a mixfix macro that calls itself.
        """
        if depth >= MAX_EXPANSION_DEPTH:
            raise SemanticError(
                f"expansion of {render_item(item)!r} is too deep; "
                "a macro with parameters may not expand into itself",
                item.span,
            )
        macro = self.lookup(signature_of(item), scope)
        if macro is None:
            raise SemanticError(f"unknown name {render_item(item)!r}", item.span)

        options = expand_call(macro, arguments_of(item))
        # The expansion is read in the *calling* scope: the arguments were
        # written there, and the body's own names resolve outward all the same.
        nodes = [self.sequence(option, scope, depth + 1) for option in options]
        if len(nodes) == 1:
            return nodes[0]
        return Choice(nodes, macro.choice_symbol or "/")
