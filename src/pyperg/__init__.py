"""Py-PERG: Parser Environment Regenerator.

Reads grammars written in MGFF and generates the lexers and parsers they
describe. The package follows the three parts of the specification:

    pyperg.mgff        lexical structure (Part 1)
    pyperg.grammar     scopes, targets, macros and expansion (Part 2)
    pyperg.semantics   character sets, built-in macros, the resolved model (Part 3)
    pyperg.generators  the backends turning a resolved grammar into code
    pyperg.diagnostics source tracking and error reporting
    pyperg.cli         the command line interface
"""

__version__ = "0.0.1"

from .diagnostics.errors import PyPergError
from .diagnostics.source import SourceFile
from .mgff.lexer import lex, lex_text

__all__ = ["PyPergError", "SourceFile", "__version__", "lex", "lex_text"]
