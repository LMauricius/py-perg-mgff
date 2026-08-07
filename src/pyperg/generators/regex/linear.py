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
from ..utils.graph import (
    callees_before_callers,
    mutually_recursive_groups,
    production_call_graph,
    productions_reachable_from,
)
from ..utils.regex import joined_as_alternatives, parenthesized_if_needed, joined_in_sequence
from ..utils.walk import top_level_parts, referenced_production_names

#: Renders a rule, given a pattern for every reference it may make. Raises
#: `GeneratorError` when the rule has no regular form of its own.
RenderRule = Callable[[Rule, Mapping[str, str]], str]

#: A pattern, or None for "matches nothing at all" — the empty language, which
#: no pattern spells and which absorbs whatever is concatenated with it.
Pattern = str | None

#: Rewrites one finished pattern, given the production it belongs to.
WrapPattern = Callable[[str, str], str]


def _wrapped_for_caller(wrap: WrapPattern, name: str, pattern: str, start: str) -> str:
    """One finished pattern, as whoever asked for it wants to read it."""
    return pattern if name == start else wrap(name, pattern)


# -- pattern algebra --------------------------------------------------------


def any_of(options: list[str]) -> Pattern:
    """Alternatives as one pattern, None when there are none."""
    return joined_as_alternatives(options, "/") if options else None


def concat_around_recursion(surrounding: str, rest: Pattern, recurses_at_end: bool) -> Pattern:
    """A surrounding pattern concatenated onto a pattern, on the side it belongs to.

    A surrounding pattern is what an alternative holds besides its recursive call, so it
    sits on the other side of that call: `recurses_at_end`, the right-linear form
    `X = A X`, puts it first, and the left-linear `X = X A` puts it last.
    """
    if rest is None:
        return None
    pieces = [surrounding, rest] if recurses_at_end else [rest, surrounding]
    return joined_in_sequence(pieces)


def zero_or_more(pattern: Pattern) -> str:
    """`A*`, which for the empty language is the empty pattern."""
    return "" if pattern is None else parenthesized_if_needed(pattern) + "*"


# -- the components a grammar is solved in ----------------------------------


def recursive_groups_callees_first(graph: dict[str, list[str]]) -> list[list[str]]:
    """Every production grouped into its component, callees first.

    A component is a set of productions that all reach each other, so its members
    can only be solved together. A depth-first finishing order visits a component
    entirely before any component that calls it, so grouping the order by
    component keeps it callee-first.
    """
    grouped: dict[str, tuple[str, ...]] = {}
    for component in mutually_recursive_groups(graph):
        key = tuple(component)
        for name in component:
            grouped[name] = key

    ordered: list[list[str]] = []
    seen: set[tuple[str, ...]] = set()
    for name in callees_before_callers(graph):
        key = grouped.get(name, (name,))
        if key not in seen:
            seen.add(key)
            ordered.append(list(key))
    return ordered


# -- reading a component's equations ----------------------------------------


class SelfEmbeddingReports:
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


class RecursionSystem:
    """One component as a linear system, ready to eliminate.

    `surrounding_patterns[X][Y]` are the alternatives of `X` that call `Y`, each without
    that call; `non_recursive_patterns[X]` are the alternatives that call no member at all.
    `recurses_at_end` says which side of its alternative the component recurses on, and
    every equation of a component must agree on it.
    """

    def __init__(self, names: list[str], recurses_at_end: bool) -> None:
        self.names = names
        self.recurses_at_end = recurses_at_end
        self.surrounding_patterns: dict[str, dict[str, list[str]]] = {
            name: {} for name in names
        }
        self.non_recursive_patterns: dict[str, list[str]] = {name: [] for name in names}

    def add_call(self, name: str, called: str, surrounding: str) -> None:
        self.surrounding_patterns[name].setdefault(called, []).append(surrounding)

    def add_non_recursive(self, name: str, pattern: str) -> None:
        self.non_recursive_patterns[name].append(pattern)


def find_recursive_call(
    parts: list[Rule], members: set[str], name: str, reports: SelfEmbeddingReports
) -> tuple[int, Rule] | None:
    """Where an alternative calls its own component, or None when it does not.

    Reports the alternative instead when the call is one no regular expression
    can express: nested inside something, in the middle of the alternative, or
    made twice.
    """
    calling_parts = [
        index
        for index, part in enumerate(parts)
        if members & set(referenced_production_names(part))
    ]
    if not calling_parts:
        return None
    if len(calling_parts) > 1:
        reports.add(name, "an alternative calls this group of productions twice")
        return None
    index = calling_parts[0]
    part = parts[index]
    if not isinstance(part, Reference):
        reports.add(
            name, "a recursive call is nested inside a repetition, a choice or a group"
        )
        return None
    if 0 < index < len(parts) - 1:
        reports.add(name, "a recursive call has text on both sides of it")
        return None
    return index, part


def read_recursive_group(
    names: list[str],
    productions: Mapping[str, Production],
    patterns: Mapping[str, str],
    render: RenderRule,
    reports: SelfEmbeddingReports,
) -> RecursionSystem | None:
    """Read a component's productions as a linear system, or None when it is none.

    Read in two passes over the same alternatives. The first only decides which
    side the component recurses on, since that settles which part of an
    alternative is the surrounding pattern; the second renders them.

    A component that is no linear system adds to `reports` and returns None, so
    that the productions at fault are gathered across the whole grammar and
    reported together.
    """
    members = set(names)
    before = len(reports.found)

    # 1. Where each recursive call sits, and therefore which form the system has.
    read: list[tuple[str, list[Rule], int | None, str]] = []
    at_start = recurses_at_end = False
    for name in names:
        for alternative in productions[name].alternatives:
            parts = top_level_parts(alternative)
            found = find_recursive_call(parts, members, name, reports)
            if found is None:
                read.append((name, parts, None, ""))
                continue
            index, reference = found
            read.append((name, parts, index, reference.name))
            # An alternative that is nothing but the call fits either form.
            if len(parts) > 1:
                at_start = at_start or index == 0
                recurses_at_end = recurses_at_end or index == len(parts) - 1
    if at_start and recurses_at_end:
        for name in names:
            reports.add(
                name,
                "the group recurses at the start of one alternative and the end of another",
            )
    if len(reports.found) > before:
        return None

    # 2. The equations themselves. What remains of an alternative once the call
    #    is taken out holds no member of the component, so it renders against the
    #    patterns already worked out.
    system = RecursionSystem(names, recurses_at_end=recurses_at_end)
    for name, parts, index, called in read:
        if index is None:
            system.add_non_recursive(name, render(Sequence(parts), patterns))
            continue
        rest = parts[:index] + parts[index + 1 :]
        system.add_call(name, called, render(Sequence(rest), patterns))
    return system


# -- solving ----------------------------------------------------------------


def eliminate_recursion(system: RecursionSystem) -> dict[str, Pattern]:
    """Eliminate the system one variable at a time, Arden's rule at each step.

    Removing a variable is two moves. Its own equation is closed first: a call on
    itself is a loop, and `X = A X + B` becomes `X = A* B`, which leaves an
    equation naming only the others. That equation is then substituted into every
    equation still calling `X`, which removes `X` from the system for good. A
    variable eliminated later still substitutes itself back into `X`'s own
    equation, so after the last one every equation is free of variables and what
    remains of each is its pattern.
    """
    surrounding_patterns = system.surrounding_patterns
    non_recursive_patterns = system.non_recursive_patterns
    recurses_at_end = system.recurses_at_end

    def without_own_loop(pattern: Pattern, loop: str) -> Pattern:
        """One term of an equation once the equation's own loop is taken out."""
        return concat_around_recursion(loop, pattern, recurses_at_end) if loop else pattern

    for name in system.names:
        # Close the equation for `name`: its own surrounding pattern is a repetition.
        loop = zero_or_more(any_of(surrounding_patterns[name].pop(name, [])))
        non_recursive = without_own_loop(any_of(non_recursive_patterns[name]), loop)
        non_recursive_patterns[name] = [non_recursive] if non_recursive is not None else []
        surrounding_patterns[name] = {
            called: [pattern]
            for called, options in surrounding_patterns[name].items()
            if (pattern := without_own_loop(any_of(options), loop)) is not None
        }

        # Substitute it into the others, which is what removes it from the system.
        for other in system.names:
            if other == name:
                continue
            calls = surrounding_patterns[other].pop(name, None)
            if calls is None:
                continue
            surrounding = any_of(calls)
            assert surrounding is not None
            if non_recursive is not None:
                non_recursive_patterns[other].append(
                    _joined_around_recursion(surrounding, non_recursive, recurses_at_end)
                )
            for called, patterns in surrounding_patterns[name].items():
                pattern = any_of(patterns)
                assert pattern is not None
                surrounding_patterns[other].setdefault(called, []).append(
                    _joined_around_recursion(surrounding, pattern, recurses_at_end)
                )

    return {name: any_of(non_recursive_patterns[name]) for name in system.names}


def _joined_around_recursion(surrounding: str, pattern: str, recurses_at_end: bool) -> str:
    """A surrounding pattern and what it multiplies, on the side the form recurses."""
    joined = concat_around_recursion(surrounding, pattern, recurses_at_end)
    assert joined is not None
    return joined


def patterns_for_all_productions(
    productions: Mapping[str, Production],
    start: str,
    render: RenderRule,
    wrap: WrapPattern | None = None,
) -> dict[str, str]:
    """Every production the start reaches, as a pattern.

    Solved component by component, callees first, so a component is reached with
    every pattern it needs already in hand.

    `wrap` gets a say over each finished pattern before anything reads it, which
    is how a production that stores its match becomes a capture group everywhere
    it is called. The start is left alone: nothing calls it.
    """
    wrap = wrap or (lambda name, pattern: pattern)
    reachable = productions_reachable_from(start, production_call_graph(dict(productions)))
    table = {name: productions[name] for name in reachable}
    graph = production_call_graph(table)

    patterns: dict[str, str] = {}
    reports = SelfEmbeddingReports()
    for component in recursive_groups_callees_first(graph):
        if len(component) == 1 and component[0] not in graph[component[0]]:
            name = component[0]
            patterns[name] = _wrapped_for_caller(
                wrap, name, render(table[name].rule, patterns), start
            )
            continue
        system = read_recursive_group(component, table, patterns, render, reports)
        if system is None:
            # The component has no pattern, and the components calling it are
            # read all the same: a grammar with two faults reports both.
            patterns.update({name: "" for name in component})
            continue
        for name, pattern in eliminate_recursion(system).items():
            if pattern is None:
                raise GeneratorError(
                    f"production {name!r} recurses without ever ending, "
                    "so it matches nothing at all"
                )
            patterns[name] = _wrapped_for_caller(wrap, name, pattern, start)
    reports.raise_if_any()
    return patterns
