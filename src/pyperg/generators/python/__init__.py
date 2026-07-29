"""A backend emitting a Python lexer and parser.

Not implemented yet.
"""

from __future__ import annotations

from pathlib import Path

from ...semantics.model import GrammarModel
from ..base import Generator


class PythonGenerator(Generator):
    """Emits a module per target, plus a package `__init__` tying them together."""

    name = "python"
    description = "emit a Python lexer and parser"

    def generate(self, model: GrammarModel, out_dir: Path) -> list[Path]:
        # 1. Emit the character sets and token rules of the `Lex` target.
        # 2. Emit one matcher function per production of the remaining targets,
        #    expanding calls on demand so recursive grammars terminate.
        # 3. Emit the package entry point and return every written path.
        raise NotImplementedError
