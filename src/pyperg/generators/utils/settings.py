"""Reading a grammar's own attributes as a backend's settings.

The `>` lines at the top of a file describe the grammar rather than any macro of
it: what the generated language is called, what it is filed under, which
extensions it claims. A backend reads them as settings, and every backend reads
them the same way, so the two spellings live here.

An attribute is a name and a list of arguments. `setting` is for the ones that
name one thing — `name(Toy)`, `section(Sources)` — and joins several arguments
with a space, so `extensions(*.toy *.t)` arrives as the list it looks like.
`values` is for the ones that are a list proper, where each argument stands on
its own.
"""

from __future__ import annotations


def setting(
    attributes: dict[str, list[str]], key: str, default: str | None = None
) -> str | None:
    """One attribute as a single value, or a default when it was not written."""
    values = attributes.get(key)
    return " ".join(values) if values else default


def values(attributes: dict[str, list[str]], key: str) -> list[str]:
    """Every argument of one attribute, or an empty list when it was not written."""
    return list(attributes.get(key) or ())
