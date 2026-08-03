"""Grammar semantics (specification Part 2): what the lines of a file mean.

The reading of a lexed file into scopes, targets and macros lives here; the
lexical structure it starts from is `pyperg.mgff`.
"""

from .macros import Macro, MacroDefinition, Scoped
from .parser import marker_of, parse
from .scope import MacroSource, Scope, TargetScope, make_source, signature_of
from .shapes import MacroShape
from .signatures import signature_to_shape, shape

__all__ = [
    "Macro",
    "MacroDefinition",
    "MacroShape",
    "MacroSource",
    "Scope",
    "Scoped",
    "TargetScope",
    "signature_to_shape",
    "make_source",
    "marker_of",
    "parse",
    "shape",
    "signature_of",
]
