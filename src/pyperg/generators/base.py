"""The interface every generator backend implements."""

from __future__ import annotations
from typing import Iterable

from abc import ABC, abstractmethod
from pathlib import Path

from ..mgff.common.order import rule_tree_macro_order
from ..mgff.semantics.macros import Macro, MacroDefinition
from ..mgff.systems.grammar import GrammarModel

class Generator(ABC):
    """A backend turning a resolved grammar into output files.

    Backends are instantiated without arguments and are stateless between runs.
    """

    #: The name the backend is selected by on the command line.
    name: str = ""

    #: One line shown by `pyperg generate --list`.
    description: str = ""

    @abstractmethod
    def generate(self, model: GrammarModel, out_dir: Path) -> Iterable[Path]:
        """Write the generated files and return their paths.

        Raises `GeneratorError` when the grammar uses something the backend
        cannot express.
        """

    def extra_macros(self) -> list[MacroDefinition]:
        """The macros this backend recognises besides the common ones.

        A backend that gives a shape a meaning of its own — a capture group, say
        — returns its definition here, and reads the calls back as a `MacroCall`
        naming it. Where they sit in the order is settled by `rule_tree_macro_order`:
        above every name, alongside `( R )+`.
        """
        return []

    def macros(self) -> list[Macro]:
        """The definitions in force while a grammar is read for this backend."""
        return rule_tree_macro_order(self.extra_macros())
