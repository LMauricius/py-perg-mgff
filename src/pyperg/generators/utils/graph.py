"""The reference graph of a target's productions.

A backend needs three things from it: which productions a starting rule can
reach, which of them take part in a cycle, and an order in which the rest can be
emitted. A backend that cannot express recursion — a regular-expression engine,
say — rejects the cycles and inlines the rest.
"""

from __future__ import annotations

from ...mgff.semantics.model import Production
from .walk import references


def reference_graph(productions: dict[str, Production]) -> dict[str, list[str]]:
    """Each production's callees, in order, with repeats removed.

    A reference to a name the table does not hold is dropped: the target reached
    it across a boundary the backend is not walking.
    """
    graph: dict[str, list[str]] = {}
    for name, production in productions.items():
        seen: list[str] = []
        for called in references(production.rule):
            if called in productions and called not in seen:
                seen.append(called)
        graph[name] = seen
    return graph


def reachable_from(start: str, graph: dict[str, list[str]]) -> set[str]:
    """Every production reachable from a starting one, the start included."""
    found: set[str] = set()
    stack = [start]
    while stack:
        name = stack.pop()
        if name in found or name not in graph:
            continue
        found.add(name)
        stack.extend(graph[name])
    return found


def cycles(graph: dict[str, list[str]]) -> list[list[str]]:
    """The strongly connected components holding more than one node, plus the
    self-referencing ones.

    Tarjan's algorithm, written iteratively so a deep grammar cannot exhaust the
    interpreter's stack.
    """
    index_of: dict[str, int] = {}
    low_of: dict[str, int] = {}
    on_stack: set[str] = set()
    component_stack: list[str] = []
    found: list[list[str]] = []
    counter = 0

    for root in graph:
        if root in index_of:
            continue
        # Each frame is a node and how far along its callees we have walked.
        work: list[tuple[str, int]] = [(root, 0)]
        while work:
            name, next_child = work[-1]
            if next_child == 0:
                index_of[name] = low_of[name] = counter
                counter += 1
                component_stack.append(name)
                on_stack.add(name)

            children = graph.get(name, [])
            if next_child < len(children):
                work[-1] = (name, next_child + 1)
                child = children[next_child]
                if child not in index_of:
                    work.append((child, 0))
                elif child in on_stack:
                    low_of[name] = min(low_of[name], index_of[child])
                continue

            # Every callee is done: close the node, and the component with it
            # when this node is the one the component was entered through.
            work.pop()
            if work:
                parent = work[-1][0]
                low_of[parent] = min(low_of[parent], low_of[name])
            if low_of[name] == index_of[name]:
                component: list[str] = []
                while True:
                    member = component_stack.pop()
                    on_stack.discard(member)
                    component.append(member)
                    if member == name:
                        break
                if len(component) > 1 or name in graph.get(name, []):
                    found.append(component)
    return found


def recursive_names(graph: dict[str, list[str]]) -> set[str]:
    """Every production taking part in a cycle."""
    return {name for component in cycles(graph) for name in component}


def topological_order(graph: dict[str, list[str]]) -> list[str]:
    """Callees before callers, for a graph with no cycles.

    Nodes inside a cycle come last, in no meaningful order; a backend that cares
    checks `cycles` first.
    """
    ordered: list[str] = []
    state: dict[str, int] = {}  # 1 while visiting, 2 when done

    for root in graph:
        if state.get(root):
            continue
        work: list[tuple[str, int]] = [(root, 0)]
        while work:
            name, next_child = work[-1]
            if next_child == 0:
                state[name] = 1
            children = graph.get(name, [])
            if next_child < len(children):
                work[-1] = (name, next_child + 1)
                child = children[next_child]
                if not state.get(child):
                    work.append((child, 0))
                continue
            work.pop()
            state[name] = 2
            ordered.append(name)
    return ordered
