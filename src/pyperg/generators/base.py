"""The interface every generator backend implements."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from ..semantics.model import GrammarModel


class Generator(ABC):
    """A backend turning a resolved grammar into output files.

    Backends are instantiated without arguments and are stateless between runs.
    """

    #: The name the backend is selected by on the command line.
    name: str = ""

    #: One line shown by `pyperg generate --list`.
    description: str = ""

    @abstractmethod
    def generate(self, model: GrammarModel, out_dir: Path) -> list[Path]:
        """Write the generated files and return their paths.

        Raises `GeneratorError` when the grammar uses something the backend
        cannot express.
        """

    def supports_target(self, target: str) -> bool:
        """Whether the backend handles a given generation phase, e.g. `Lex`."""
        return True
