"""Py-PERG: Parser Environment Regenerator.

Reads grammars written in MGFF and generates the lexers and parsers they
describe. The package follows the three parts of the specification:

    pyperg.mgff        lexical structure (Part 1) and grammar semantics (Part 2)
    pyperg.semantics   shapes, names, expansion, built-ins (Parts 2 and 3)
    pyperg.generators  the backends turning a resolved grammar into code
    pyperg.diagnostics source tracking and error reporting
    pyperg.cli         the command line interface
"""

__version__ = "0.0.1"

from .diagnostics.errors import PyPergError
from .diagnostics.source import SourceFile
from .mgff.lexer import lex, lex_text

__all__ = ["PyPergError", "SourceFile", "__version__", "lex", "lex_text"]
