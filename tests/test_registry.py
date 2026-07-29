"""Generator discovery."""

import pytest

from pyperg.diagnostics.errors import GeneratorError
from pyperg.generators import registry
from pyperg.generators.base import Generator


def test_builtin_generators_are_available():
    backends = registry.available()
    assert {"dump", "python"} <= set(backends)
    assert all(issubclass(b, Generator) for b in backends.values())


def test_get_instantiates_a_backend():
    backend = registry.get("dump")
    assert backend.name == "dump"


def test_unknown_generator_is_reported():
    with pytest.raises(GeneratorError, match="unknown generator"):
        registry.get("nonexistent")
