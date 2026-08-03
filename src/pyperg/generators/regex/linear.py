"""Solving a recursive grammar into one pattern, where that is possible at all.

A regular expression has no recursion, but a grammar may still describe a
regular language while writing itself recursively:

    d Digits = 0-9 Digits
             / 0-9

That is **right-linear** — every recursive call sits at the end of its
alternative — and Arden's rule turns it into a repetition:

    X = A X + B   ⇒   X = A* B          right-linear
    X = X A + B   ⇒   X = B A*          left-linear

What has no regular form is **self-embedding**: an alternative that recurses
with something on both sides of the call, such as `d Expr = \\( Expr \\)`. Those
grammars are the ones this backend reports, naming the productions at fault.

The productions are solved a **strongly connected component** at a time, in
callee-first order, so by the time a component is reached everything it calls is
already a finished pattern and only its own members are still unknown. A
component of one production that does not call itself is simply rendered; a
component that recurses is checked for linearity and then eliminated, one
variable at a time, in the manner of Gaussian elimination:

```mermaid
flowchart LR
    R[reachable from the start] --> C[components, callees first]
    C --> P{recursive?}
    P -- no --> D[render directly]
    P -- yes --> L{left- or right-linear?}
    L -- no --> E[self-embedding: report]
    L -- yes --> A["eliminate by Arden's rule"]
```

Within a component the order of alternatives is not preserved: elimination
rewrites the equations, and `|` versus `/` no longer has anything to attach to.
Outside one, both markers keep the meaning `utils.regex` gives them.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping

from ...diagnostics.errors import GeneratorError
from ...mgff.common.rules import Reference, Rule, Sequence
from ...mgff.semantics.model import Production
from ..utils.graph import cycles, reachable_from, reference_graph, topological_order
from ..utils.regex import alternation, atom, concatenation
from ..utils.walk import flatten, references

#: Renders a rule, given a pattern for every reference it may make. Raises
#: `GeneratorError` when the rule has no regular form of its own.
Render = Callable[[Rule, Mapping[str, str]], str]

#: A pattern, or None for "matches nothing at all" — the empty language, which
#: no pattern spells and which absorbs whatever is concatenated with it.
Pattern = str | None


# -- pattern algebra --------------------------------------------------------


def union(options: list[str]) -> Pattern:
    """Alternatives as one pattern, None when there are none."""
    return alternation(options, "/") if options else None


def times(coefficient: str, rest: Pattern, at_end: bool) -> Pattern:
    """A coefficient concatenated onto a pattern, on the side it belongs to.

    A coefficient is what an alternative holds besides its recursive call, so it
    sits on the other side of that call: `at_end`, the right-linear form
    `X = A X`, puts it first, and the left-linear `X = X A` puts it last.
    """
    if rest is None:
        return None
    pieces = [coefficient, rest] if at_end else [rest, coefficient]
    return concatenation(pieces)


def repeated(pattern: Pattern) -> str:
    """`A*`, which for the empty language is the empty pattern."""
    return "" if pattern is None else atom(pattern) + "*"


# -- the components a grammar is solved in ----------------------------------


def components_in_order(graph: dict[str, list[str]]) -> list[list[str]]:
    """Every production grouped into its component, callees first.

    A component is a set of productions that all reach each other, so its members
    can only be solved together. A depth-first finishing order visits a component
    entirely before any component that calls it, so grouping the order by
    component keeps it callee-first.
    """
    grouped: dict[str, tuple[str, ...]] = {}
    for component in cycles(graph):
        key = tuple(component)
        for name in component:
            grouped[name] = key

    ordered: list[list[str]] = []
    seen: set[tuple[str, ...]] = set()
    for name in topological_order(graph):
        key = grouped.get(name, (name,))
        if key not in seen:
            seen.add(key)
            ordered.append(list(key))
    return ordered


# -- reading a component's equations ----------------------------------------


class Culprits:
    """The alternatives that recurse in a way no regular expression can match."""

    def __init__(self) -> None:
        self.found: list[tuple[str, str]] = []

    def add(self, name: str, reason: str) -> None:
        if (name, reason) not in self.found:
            self.found.append((name, reason))

    def raise_if_any(self) -> None:
        """Report every culprit at once, since one rarely comes alone."""
        if not self.found:
            return
        listed = "\n".join(f"  {name}: {reason}" for name, reason in self.found)
        raise GeneratorError(
            "this grammar is not regular, so it cannot be written as one "
            "expression:\n"
            f"{listed}\n"
            "A regular expression has no recursion. A production may still call "
            "itself at the very start or the very end of an alternative, which "
            "is a repetition in disguise, but a call with something on both "
            "sides of it is not."
        )


class Equations:
    """One component as a linear system, ready to eliminate.

    `coefficients[X][Y]` are the alternatives of `X` that call `Y`, each without
    that call; `constants[X]` are the alternatives that call no member at all.
    `at_end` says which side of its alternative the component recurses on, and
    every equation of a component must agree on it.
    """

    def __init__(self, names: list[str], at_end: bool) -> None:
        self.names = names
        self.at_end = at_end
        self.coefficients: dict[str, dict[str, list[str]]] = {n: {} for n in names}
        self.constants: dict[str, list[str]] = {n: [] for n in names}

    def add_call(self, name: str, called: str, coefficient: str) -> None:
        self.coefficients[name].setdefault(called, []).append(coefficient)

    def add_constant(self, name: str, pattern: str) -> None:
        self.constants[name].append(pattern)


def read_alternative(
    parts: list[Rule], members: set[str], name: str, culprits: Culprits
) -> tuple[int, Rule] | None:
    """Where an alternative calls its own component, or None when it does not.

    Reports the alternative instead when the call is one no regular expression
    can express: nested inside something, in the middle of the alternative, or
    made twice.
    """
    hits = [index for index, part in enumerate(parts) if members & set(references(part))]
    if not hits:
        return None
    if len(hits) > 1:
        culprits.add(name, "an alternative calls this group of productions twice")
        return None
    index = hits[0]
    part = parts[index]
    if not isinstance(part, Reference):
        culprits.add(
            name, "a recursive call is nested inside a repetition, a choice or a group"
        )
        return None
    if 0 < index < len(parts) - 1:
        culprits.add(name, "a recursive call has text on both sides of it")
        return None
    return index, part


def read_component(
    names: list[str],
    productions: Mapping[str, Production],
    patterns: Mapping[str, str],
    render: Render,
    culprits: Culprits,
) -> Equations | None:
    """Read a component's productions as a linear system, or None when it is none.

    Read in two passes over the same alternatives. The first only decides which
    side the component recurses on, since that settles which part of an
    alternative is the coefficient; the second renders them.

    A component that is no linear system adds to `culprits` and returns None, so
    that the productions at fault are gathered across the whole grammar and
    reported together.
    """
    members = set(names)
    before = len(culprits.found)

    # 1. Where each recursive call sits, and therefore which form the system has.
    read: list[tuple[str, list[Rule], int | None, str]] = []
    at_start = at_end = False
    for name in names:
        for alternative in productions[name].alternatives:
            parts = flatten(alternative)
            found = read_alternative(parts, members, name, culprits)
            if found is None:
                read.append((name, parts, None, ""))
                continue
            index, reference = found
            read.append((name, parts, index, reference.name))
            # An alternative that is nothing but the call fits either form.
            if len(parts) > 1:
                at_start = at_start or index == 0
                at_end = at_end or index == len(parts) - 1
    if at_start and at_end:
        for name in names:
            culprits.add(
                name,
                "the group recurses at the start of one alternative and the end of another",
            )
    if len(culprits.found) > before:
        return None

    # 2. The equations themselves. What remains of an alternative once the call
    #    is taken out holds no member of the component, so it renders against the
    #    patterns already worked out.
    equations = Equations(names, at_end=at_end)
    for name, parts, index, called in read:
        if index is None:
            equations.add_constant(name, render(Sequence(parts), patterns))
            continue
        rest = parts[:index] + parts[index + 1 :]
        equations.add_call(name, called, render(Sequence(rest), patterns))
    return equations


# -- solving ----------------------------------------------------------------


def solve_component(equations: Equations) -> dict[str, Pattern]:
    """Eliminate the system one variable at a time, Arden's rule at each step.

    Removing a variable is two moves. Its own equation is closed first: a call on
    itself is a loop, and `X = A X + B` becomes `X = A* B`, which leaves an
    equation naming only the others. That equation is then substituted into every
    equation still calling `X`, which removes `X` from the system for good. A
    variable eliminated later still substitutes itself back into `X`'s own
    equation, so after the last one every equation is free of variables and what
    remains of each is its pattern.
    """
    coefficients = equations.coefficients
    constants = equations.constants
    at_end = equations.at_end

    def closed(pattern: Pattern, loop: str) -> Pattern:
        """One term of an equation once the equation's own loop is taken out."""
        return times(loop, pattern, at_end) if loop else pattern

    for name in equations.names:
        # Close the equation for `name`: its own coefficient is a repetition.
        loop = repeated(union(coefficients[name].pop(name, [])))
        constant = closed(union(constants[name]), loop)
        constants[name] = [constant] if constant is not None else []
        coefficients[name] = {
            called: [pattern]
            for called, options in coefficients[name].items()
            if (pattern := closed(union(options), loop)) is not None
        }

        # Substitute it into the others, which is what removes it from the system.
        for other in equations.names:
            if other == name:
                continue
            calls = coefficients[other].pop(name, None)
            if calls is None:
                continue
            coefficient = union(calls)
            assert coefficient is not None
            if constant is not None:
                constants[other].append(_joined(coefficient, constant, at_end))
            for called, patterns in coefficients[name].items():
                pattern = union(patterns)
                assert pattern is not None
                coefficients[other].setdefault(called, []).append(
                    _joined(coefficient, pattern, at_end)
                )

    return {name: union(constants[name]) for name in equations.names}


def _joined(coefficient: str, pattern: str, at_end: bool) -> str:
    """A coefficient and what it multiplies, on the side the form recurses."""
    joined = times(coefficient, pattern, at_end)
    assert joined is not None
    return joined


def patterns_for(
    productions: Mapping[str, Production], start: str, render: Render
) -> dict[str, str]:
    """Every production the start reaches, as a pattern.

    Solved component by component, callees first, so a component is reached with
    every pattern it needs already in hand.
    """
    reachable = reachable_from(start, reference_graph(dict(productions)))
    table = {name: productions[name] for name in reachable}
    graph = reference_graph(table)

    patterns: dict[str, str] = {}
    culprits = Culprits()
    for component in components_in_order(graph):
        if len(component) == 1 and component[0] not in graph[component[0]]:
            name = component[0]
            patterns[name] = render(table[name].rule, patterns)
            continue
        equations = read_component(component, table, patterns, render, culprits)
        if equations is None:
            # The component has no pattern, and the components calling it are
            # read all the same: a grammar with two faults reports both.
            patterns.update({name: "" for name in component})
            continue
        for name, pattern in solve_component(equations).items():
            if pattern is None:
                raise GeneratorError(
                    f"production {name!r} recurses without ever ending, "
                    "so it matches nothing at all"
                )
            patterns[name] = pattern
    culprits.raise_if_any()
    return patterns
