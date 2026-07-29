"""Built-in macros and attributes (Part 3).

Not implemented yet.

These are macros whose expansion is defined by the generator rather than by
MGFF. Every target that treats macros as matching rules provides the repetition
and choice forms; a domain-specific dialect may add built-ins of its own.
"""

from __future__ import annotations

# Rule-matching built-ins, present in every target with productions.
REPETITION_MARKERS: dict[str, tuple[int, int | None]] = {
    "+": (1, None),  # one or more
    "*": (0, None),  # zero or more
    "?": (0, 1),  # optional
}

CHOICE_MARKERS: frozenset[str] = frozenset({"|", "/"})  # length-based, order-based

# Attributes the established targets understand. Their meaning is
# generator-specific; a backend may recognise more.
KNOWN_ATTRIBUTES: frozenset[str] = frozenset({"token", "skip", "string"})


def is_builtin(name: str) -> bool:
    """Whether a name is provided by the generator rather than by the grammar."""
    raise NotImplementedError
