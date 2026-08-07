"""Generator discovery."""

import pytest

from pyperg.diagnostics.errors import GeneratorError
from pyperg.generators import registry
from pyperg.generators.base import Generator


def test_builtin_generators_are_available():
    backends = registry.available_generators()
    assert {"dump", "kate", "python"} <= set(backends)
    assert all(issubclass(backend, Generator) for backend in backends.values())


def test_load_generator_instantiates_a_backend():
    backend = registry.load_generator("dump")
    assert backend.name == "dump"


def test_unknown_generator_is_reported():
    with pytest.raises(GeneratorError, match="unknown generator"):
        registry.load_generator("nonexistent")
