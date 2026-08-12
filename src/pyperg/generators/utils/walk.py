"""Reading and rewriting rule trees.

The functions here answer the questions a backend keeps asking of a rule: what
does it reference, can it match nothing, and is it in truth a fixed string?

**Literal fusing** deserves a note. MGFF has no multi-character literal item: a
part of a character set is one character, so the alternative `< =` arrives as
two single-character character-set nodes. A backend that wants to emit "match
the string `<=`" must first merge them, which is what `merge_adjacent_literals` does.
Without it every literal longer than one character would fall through to a
regular expression.

A `MacroCall` belongs to whichever macro built it, so nothing here reads one
except through its arguments, which are ordinary rules.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator

from ...mgff.common.characters import character_set_matched_by
from ...mgff.common.rules import (
    Choice,
    MacroCall,
    Rule,
    Reference,
    Repetition,
    Sequence,
)
from ...mgff.systems.model import Production

def walk_rule_tree(node: Rule) -> Iterator[Rule]:
    """Every node of a tree, the node itself first."""
    yield node
    if isinstance(node, Sequence):
        for item in node.items:
            yield from walk_rule_tree(item)
    elif isinstance(node, Repetition):
        yield from walk_rule_tree(node.body)
    elif isinstance(node, Choice):
        for option in node.options:
            yield from walk_rule_tree(option)
    elif isinstance(node, MacroCall):
        for argument in node.arguments:
            yield from walk_rule_tree(argument)


def rewrite_rule_tree(node: Rule, replace: Callable[[Rule], Rule | None]) -> Rule:
    """A tree with every node `replace` answers for swapped for its answer.

    `replace` is asked about a node before its children, and a node it answers
    for is taken whole: what replaces a subtree is not walked into again. A
    `MacroCall` is rebuilt around its arguments, since those are ordinary rules,
    and the item it was written as is carried across untouched.
    """
    found = replace(node)
    if found is not None:
        return found
    if isinstance(node, Sequence):
        return Sequence([rewrite_rule_tree(item, replace) for item in node.items])
    if isinstance(node, Repetition):
        return Repetition(
            rewrite_rule_tree(node.body, replace), node.minimum, node.maximum, node.marker
        )
    if isinstance(node, Choice):
        return Choice([rewrite_rule_tree(option, replace) for option in node.options], node.symbol)
    if isinstance(node, MacroCall) and node.arguments:
        return MacroCall(
            node.macro, node.item, [rewrite_rule_tree(one, replace) for one in node.arguments]
        )
    return node


def referenced_production_names(node: Rule) -> list[str]:
    """The names a rule calls, in order, with repeats kept."""
    return [found.name for found in walk_rule_tree(node) if isinstance(found, Reference)]


def can_match_empty(node: Rule, find_production: Callable[[str], Production | None]) -> bool:
    """Whether a rule can match nothing at all.

    A reference is followed through `find_production`; a reference that leads nowhere, or
    back to itself, is treated as not nullable, which is the safe answer for a
    backend deciding whether it must consume input.
    """
    return _can_match_empty(node, find_production, seen=set())


def _can_match_empty(
    node: Rule, find_production: Callable[[str], Production | None], seen: set[str]
) -> bool:
    if isinstance(node, MacroCall):
        # A character set consumes a character. Any other macro is nullable only
        # when everything it wraps is, and one wrapping nothing is not: a
        # backend deciding whether it must consume input wants the safe answer.
        if character_set_matched_by(node) is not None:
            return False
        return bool(node.arguments) and all(
            _can_match_empty(argument, find_production, seen) for argument in node.arguments
        )
    if isinstance(node, Sequence):
        return all(_can_match_empty(item, find_production, seen) for item in node.items)
    if isinstance(node, Repetition):
        return node.minimum == 0 or _can_match_empty(node.body, find_production, seen)
    if isinstance(node, Choice):
        return any(_can_match_empty(option, find_production, seen) for option in node.options)
    # A reference, followed once: a cycle means it must consume something to
    # come back round, so reporting it as non-nullable is right.
    if node.name in seen:
        return False
    production = find_production(node.name)
    if production is None:
        return False
    return _can_match_empty(production.rule, find_production, seen | {node.name})


def top_level_parts(node: Rule) -> list[Rule]:
    """A node as a flat sequence, with nested sequences merged in.

    Sequences nest freely — a subgroup inside a subgroup — and nesting says
    nothing about matching, so a backend reading a rule left to right wants it
    flat.
    """
    if not isinstance(node, Sequence):
        return [node]
    out: list[Rule] = []
    for item in node.items:
        out.extend(top_level_parts(item))
    return out


def single_character(node: Rule) -> str | None:
    """The one character a node matches, or None when it matches anything else."""
    characters = character_set_matched_by(node)
    if characters is not None:
        return characters.single_character
    if isinstance(node, Sequence) and len(node.items) == 1:
        return single_character(node.items[0])
    return None


def literal_of(node: Rule) -> str | None:
    """The fixed string a node matches, or None when it is not a fixed string.

    `< =` gives `"<="`; a range, a repetition or a reference gives None.
    """
    parts = top_level_parts(node)
    if not parts:
        return None
    characters: list[str] = []
    for part in parts:
        character = single_character(part)
        if character is None:
            return None
        characters.append(character)
    return "".join(characters)


def merge_adjacent_literals(nodes: list[Rule]) -> list[Rule]:
    """Merge runs of single-character nodes into one `Sequence` each.

    The result is still a list of nodes; what changes is that a run that spells
    a string is now one node, which `literal_of` reports as that string.
    """
    fused: list[Rule] = []
    run: list[Rule] = []

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
