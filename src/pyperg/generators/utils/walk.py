"""Reading and rewriting rule trees.

The functions here answer the questions a backend keeps asking of a rule: what
does it reference, can it match nothing, and is it in truth a fixed string?

**Literal fusing** deserves a note. MGFF has no multi-character literal item: a
part of a character set is one character, so the alternative `< =` arrives as
two single-character character-set nodes. A backend that wants to emit "match
the string `<=`" must first merge them, which is what `fuse_literals` does.
Without it every literal longer than one character would fall through to a
regular expression.

A `MacroCall` belongs to whichever macro built it, so nothing here reads one
except through its arguments, which are ordinary rules.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator

from ...mgff.semantics.charset import character_set_of
from ...mgff.semantics.model import (
    Choice,
    MacroCall,
    Node,
    Production,
    Reference,
    Repetition,
    Sequence,
)

def walk(node: Node) -> Iterator[Node]:
    """Every node of a tree, the node itself first."""
    yield node
    if isinstance(node, Sequence):
        for item in node.items:
            yield from walk(item)
    elif isinstance(node, Repetition):
        yield from walk(node.body)
    elif isinstance(node, Choice):
        for option in node.options:
            yield from walk(option)
    elif isinstance(node, MacroCall):
        for argument in node.arguments:
            yield from walk(argument)


def references(node: Node) -> list[str]:
    """The names a rule calls, in order, with repeats kept."""
    return [found.name for found in walk(node) if isinstance(found, Reference)]


def nullable(node: Node, lookup: Callable[[str], Production | None]) -> bool:
    """Whether a rule can match nothing at all.

    A reference is followed through `lookup`; a reference that leads nowhere, or
    back to itself, is treated as not nullable, which is the safe answer for a
    backend deciding whether it must consume input.
    """
    return _nullable(node, lookup, seen=set())


def _nullable(
    node: Node, lookup: Callable[[str], Production | None], seen: set[str]
) -> bool:
    if isinstance(node, MacroCall):
        # A character set consumes a character. Any other macro is nullable only
        # when everything it wraps is, and one wrapping nothing is not: a
        # backend deciding whether it must consume input wants the safe answer.
        if character_set_of(node) is not None:
            return False
        return bool(node.arguments) and all(
            _nullable(argument, lookup, seen) for argument in node.arguments
        )
    if isinstance(node, Sequence):
        return all(_nullable(item, lookup, seen) for item in node.items)
    if isinstance(node, Repetition):
        return node.minimum == 0 or _nullable(node.body, lookup, seen)
    if isinstance(node, Choice):
        return any(_nullable(option, lookup, seen) for option in node.options)
    # A reference, followed once: a cycle means it must consume something to
    # come back round, so reporting it as non-nullable is right.
    if node.name in seen:
        return False
    production = lookup(node.name)
    if production is None:
        return False
    return _nullable(production.rule, lookup, seen | {node.name})


def flatten(node: Node) -> list[Node]:
    """A node as a flat sequence, with nested sequences merged in.

    Sequences nest freely — a subgroup inside a subgroup — and nesting says
    nothing about matching, so a backend reading a rule left to right wants it
    flat.
    """
    if not isinstance(node, Sequence):
        return [node]
    out: list[Node] = []
    for item in node.items:
        out.extend(flatten(item))
    return out


def single_character(node: Node) -> str | None:
    """The one character a node matches, or None when it matches anything else."""
    characters = character_set_of(node)
    if characters is not None:
        return characters.single_character
    if isinstance(node, Sequence) and len(node.items) == 1:
        return single_character(node.items[0])
    return None


def literal_of(node: Node) -> str | None:
    """The fixed string a node matches, or None when it is not a fixed string.

    `< =` gives `"<="`; a range, a repetition or a reference gives None.
    """
    parts = flatten(node)
    if not parts:
        return None
    characters = [single_character(part) for part in parts]
    if any(character is None for character in characters):
        return None
    return "".join(characters)  # type: ignore[arg-type]


def fuse_literals(nodes: list[Node]) -> list[Node]:
    """Merge runs of single-character nodes into one `Sequence` each.

    The result is still a list of nodes; what changes is that a run that spells
    a string is now one node, which `literal_of` reports as that string.
    """
    fused: list[Node] = []
    run: list[Node] = []

    def flush() -> None:
        """Close the run in progress, unwrapping a run of one."""
        if not run:
            return
        fused.append(run[0] if len(run) == 1 else Sequence(list(run)))
        run.clear()

    for node in nodes:
        if single_character(node) is not None:
            run.append(node)
        else:
            flush()
            fused.append(node)
    flush()
    return fused
