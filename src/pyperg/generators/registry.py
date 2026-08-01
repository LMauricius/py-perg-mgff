"""Discovery of generator backends.

Backends are found through the `pyperg.generators` entry point group, so a
third-party package registers one by declaring it in its own metadata:

    [project.entry-points."pyperg.generators"]
    mybackend = "mypackage.backend:MyGenerator"

The built-in backends are registered the same way in this project's
`pyproject.toml`, and are also listed here so an uninstalled source checkout
still finds them.
"""

from __future__ import annotations

import sys
from importlib import import_module
from importlib.metadata import entry_points

from ..diagnostics.errors import GeneratorError
from .base import Generator

ENTRY_POINT_GROUP = "pyperg.generators"

# Fallback for a checkout that has not been installed: name -> "module:attribute".
BUILTIN_GENERATORS: dict[str, str] = {
    "dump": "pyperg.generators.dump:DumpGenerator",
    "kate": "pyperg.generators.kate:KateGenerator",
    "python": "pyperg.generators.python:PythonGenerator",
}


def _load(reference: str) -> type[Generator]:
    """Import a `module:attribute` reference."""
    module_name, _, attribute = reference.partition(":")
    return getattr(import_module(module_name), attribute)


def available() -> dict[str, type[Generator]]:
    """Every backend that can be loaded, by name.

    Installed entry points win over the built-in fallbacks, so a package may
    replace a built-in backend with its own.
    """
    found: dict[str, type[Generator]] = {
        name: _load(reference) for name, reference in BUILTIN_GENERATORS.items()
    }
    for entry in entry_points(group=ENTRY_POINT_GROUP):
        try:
            found[entry.name] = entry.load()
        except Exception as err:  # a broken third-party backend must not break the tool
            print(f"pyperg: could not load generator {entry.name!r}: {err}", file=sys.stderr)
    return found


def get(name: str) -> Generator:
    """Instantiate a backend by name."""
    backends = available()
    if name not in backends:
        known = ", ".join(sorted(backends)) or "none"
        raise GeneratorError(f"unknown generator {name!r}; available: {known}")
    return backends[name]()
