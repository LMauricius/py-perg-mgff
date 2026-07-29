"""The resolved grammar handed to a generator.

Not implemented yet.

This is the boundary between the front end and the backends: everything MGFF
defines has been read and resolved, and nothing here refers to the concrete
syntax any more.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..mgff.ast import Preference


@dataclass(slots=True)
class Production:
    """A macro a target treats as a matching rule."""

    name: str
    alternatives: list[object] = field(default_factory=list)  # resolved rule trees
    preference: Preference = Preference.ORDER
    attributes: dict[str, list[str]] = field(default_factory=dict)


@dataclass(slots=True)
class Target:
    """One generation phase, typically `Lex` for tokens and `Parse` for grammar."""

    name: str
    productions: dict[str, Production] = field(default_factory=dict)
    matches_characters: bool = False  # whether character sets apply here


@dataclass(slots=True)
class GrammarModel:
    """The whole resolved grammar."""

    name: str
    targets: list[Target] = field(default_factory=list)


def resolve(grammar: object) -> GrammarModel:
    """Turn a parsed grammar into the resolved model.

    Builds the symbol tables, classifies every item by shape, checks that calls
    resolve and that attributes are understood, then collects the productions
    per target. Calls are *not* expanded here: expansion happens on demand,
    since the call graph may contain cycles.
    """
    raise NotImplementedError
