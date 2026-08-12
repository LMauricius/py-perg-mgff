"""Left recursion, and the part of it ANTLR will not take.

ANTLR 4 reads a **directly** left-recursive rule as written and derives operator
precedence from the order of its alternatives, which is the idiomatic way to
spell an expression grammar:

    expr : expr '*' expr
         | expr '+' expr
         | INT
         ;

So a production that calls itself is left alone. What ANTLR genuinely refuses is
**indirect** left recursion — a cycle running through two or more rules, where
there is no single rule for it to rewrite:

    d Expr = Term + Expr / Term
    d Term = Expr * Term / Number

Such a cycle is removed here, and removing it takes both halves of the classical
treatment. Substitution in the manner of Paull turns the cycle into direct
recursion, one member at a time; that member's direct recursion is then closed
into a repetition, so the next substitution cannot bring the cycle back:

    A = A α | β   ⇒   A : β ( α )* ;

The repetition is why no rule is invented for it: ANTLR's `*` says in one place
what a generated helper rule would otherwise say in two. Within such a component
the order of alternatives no longer survives, which is the same price
`regex/linear.py` pays for the same kind of rewriting.

A cycle whose recursion does not sit at the very start of an alternative — nested
in a group, or reached past something that may match nothing — has no such form,
and is reported naming the productions at fault.
"""

from __future__ import annotations

from collections.abc import Callable

from ...diagnostics.errors import GeneratorError
from ...mgff.common.rules import Choice, Reference, Repetition, Rule, Sequence
from ...mgff.systems.model import Production
from ..utils.graph import mutually_recursive_groups
from ..utils.walk import can_match_empty, top_level_parts

FindProduction = Callable[[str], Production | None]

#: How many alternatives one production may grow to before substitution is
#: called runaway. A cycle of a few rules stays far below it; one that does not
#: is reported rather than expanded until the machine gives out.
MAX_ALTERNATIVES = 256


def _alternative_parts(production: Production) -> list[list[Rule]]:
    """Every alternative of a production as a flat list of parts."""
    return [top_level_parts(alternative) for alternative in production.alternatives]


def _as_rule(parts: list[Rule]) -> Rule:
    """A list of parts as one node, unwrapped when there is only one."""
    return parts[0] if len(parts) == 1 else Sequence(list(parts))


def _joined(options: list[Rule], symbol: str) -> Rule:
    """Alternatives as one node, unwrapped when there is only one."""
    return options[0] if len(options) == 1 else Choice(list(options), symbol)


# -- what a rule may begin with ----------------------------------------------


def left_corner_names(node: Rule, find_production: FindProduction) -> list[str]:
    """The productions a rule may begin its match with.

    The scan runs left to right and stops at the first part that has to consume
    something: what follows a part that must match cannot be at the start. A part
    that may match nothing is passed over, so `( Space )? Expr` begins with
    `Expr` as well.
    """
    found: list[str] = []
    _collect_left_corners(node, find_production, found)
    return found


def _collect_left_corners(node: Rule, find_production: FindProduction, found: list[str]) -> None:
    for part in top_level_parts(node):
        if isinstance(part, Reference):
            if part.name not in found:
                found.append(part.name)
        elif isinstance(part, Choice):
            for option in part.options:
                _collect_left_corners(option, find_production, found)
        elif isinstance(part, Repetition):
            _collect_left_corners(part.body, find_production, found)
        if not can_match_empty(part, find_production):
            return


def left_corner_graph(rules: dict[str, Production]) -> dict[str, list[str]]:
    """Which productions each one may begin with, kept to the table given.

    A name outside the table is dropped, exactly as `production_call_graph`
    drops one: a parser rule beginning with a token begins with something the
    cycles here are not about.
    """
    find_production = rules.get
    graph: dict[str, list[str]] = {}
    for name, production in rules.items():
        corners: list[str] = []
        for alternative in production.alternatives:
            for found in left_corner_names(alternative, find_production):
                if found in rules and found not in corners:
                    corners.append(found)
        graph[name] = corners
    return graph


# -- reporting ---------------------------------------------------------------


class LeftRecursionReports:
    """The productions whose left recursion has no form ANTLR accepts."""

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
            "ANTLR cannot read the left recursion in this grammar:\n"
            f"{listed}\n"
            "A rule may call itself at the very start of an alternative, and it "
            "needs at least one alternative that does not. Recursion reached "
            "through a group, or past something that may match nothing, has no "
            "form ANTLR accepts."
        )


#: What is said of a call the rewriting cannot take hold of.
_NOT_AT_THE_START = (
    "a recursive call is reached through a group, or past something that may "
    "match nothing"
)


def _is_substitutable(
    name: str,
    production: Production,
    members: set[str],
    find_production: FindProduction,
    reports: LeftRecursionReports,
) -> bool:
    """Whether every alternative recursing into the component starts with the call.

    Nothing else is asked of it here: an alternative that is only the call, and
    a rule whose every alternative recurses, are both ordinary in a cycle and are
    dealt with by the substitution itself.
    """
    readable = True
    for parts in _alternative_parts(production):
        if not set(left_corner_names(_as_rule(parts), find_production)) & members:
            continue
        first = parts[0] if parts else None
        if not (isinstance(first, Reference) and first.name in members):
            reports.add(name, _NOT_AT_THE_START)
            readable = False
    return readable


def _check_antlr_reads_it(
    name: str,
    production: Production,
    find_production: FindProduction,
    reports: LeftRecursionReports,
) -> None:
    """The shapes ANTLR refuses in a rule it is left to read as left-recursive."""
    non_recursive = 0
    for parts in _alternative_parts(production):
        if name not in left_corner_names(_as_rule(parts), find_production):
            non_recursive += 1
            continue
        first = parts[0] if parts else None
        if not (isinstance(first, Reference) and first.name == name):
            reports.add(name, _NOT_AT_THE_START)
        elif len(parts) == 1:
            reports.add(name, "an alternative is nothing but the recursive call")
    if non_recursive == 0:
        reports.add(name, "every alternative recurses, so it never ends")


# -- the rewriting -----------------------------------------------------------


def rewrite_indirect_left_recursion(rules: dict[str, Production]) -> None:
    """Remove every left-recursive cycle running through more than one rule.

    Direct recursion is left as it stands, since ANTLR reads it; the cycles are
    found in the *left-corner* graph rather than the call graph, because a rule
    calling another at the end of an alternative is no cycle ANTLR minds.
    """
    find_production = rules.get
    reports = LeftRecursionReports()
    components = [
        component
        for component in mutually_recursive_groups(left_corner_graph(rules))
        if len(component) > 1
    ]

    for component in components:
        members = set(component)
        # Every member is read before any is judged, so a grammar with several
        # faults reports them all rather than the first.
        readable = [
            _is_substitutable(name, rules[name], members, find_production, reports)
            for name in component
        ]
        if all(readable):
            _remove_cycle(component, rules, find_production, reports)

    # What is left directly recursive has to be a shape ANTLR reads.
    for name, corners in left_corner_graph(rules).items():
        if name in corners:
            _check_antlr_reads_it(name, rules[name], find_production, reports)
    reports.raise_if_any()


def _remove_cycle(
    component: list[str],
    rules: dict[str, Production],
    find_production: FindProduction,
    reports: LeftRecursionReports,
) -> None:
    """Substitute the component's members into each other, closing each in turn."""
    for index, name in enumerate(component):
        for earlier in component[:index]:
            _substitute(name, earlier, rules, reports)
            if reports.found:
                return
        _close_direct_recursion(name, rules[name], find_production, reports)
        if reports.found:
            return


def _substitute(
    name: str, earlier: str, rules: dict[str, Production], reports: LeftRecursionReports
) -> None:
    """Spell an earlier member out wherever this one begins with it."""
    production = rules[name]
    earlier_parts = _alternative_parts(rules[earlier])
    grown: list[Rule] = []
    for parts in _alternative_parts(production):
        first = parts[0] if parts else None
        if not (isinstance(first, Reference) and first.name == earlier):
            grown.append(_as_rule(parts))
            continue
        rest = parts[1:]
        grown.extend(_as_rule(list(opening) + rest) for opening in earlier_parts)
    if len(grown) > MAX_ALTERNATIVES:
        reports.add(
            name,
            "removing the cycle it is in would take more alternatives than a "
            "readable grammar holds",
        )
        return
    production.alternatives = grown


def _close_direct_recursion(
    name: str,
    production: Production,
    find_production: FindProduction,
    reports: LeftRecursionReports,
) -> None:
    """Turn `A = A α | β` into the single alternative `β ( α )*`.

    This is what stops a substituted cycle coming back: once the member no longer
    calls itself at the start, nothing spelled out of it can.
    """
    symbol = production.choice_symbol or "/"
    tails: list[Rule] = []
    openings: list[Rule] = []
    for parts in _alternative_parts(production):
        first = parts[0] if parts else None
        if isinstance(first, Reference) and first.name == name:
            tails.append(_as_rule(parts[1:]))
        else:
            openings.append(_as_rule(parts))
    if not tails:
        return
    if not openings:
        reports.add(name, "every alternative recurses, so it never ends")
        return
    if any(can_match_empty(tail, find_production) for tail in tails):
        reports.add(
            name, "an alternative is nothing but the recursive call"
        )
        return
    body = Repetition(_joined(tails, symbol), minimum=0, maximum=None, marker="*")
    production.alternatives = [Sequence([_joined(openings, symbol), body])]
    production.choice_symbol = None
