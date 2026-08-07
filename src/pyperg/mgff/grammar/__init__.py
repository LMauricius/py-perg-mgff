"""Grammar semantics (specification Part 2): what the lines of a file mean.

The reading of a lexed file into scopes, targets and macros lives here; the
lexical structure it starts from is `pyperg.mgff`.
"""

from .macros import Macro, MacroDefinition, ScopeLookupPoint
from .parser import line_marker_of, parse
from .scope import MacroSource, Scope, TargetScope, macro_source_from_head, signature_of
from .shapes import MacroShape
from .signatures import definition_shape, make_shape

__all__ = [
    "Macro",
    "MacroDefinition",
    "MacroShape",
    "MacroSource",
    "Scope",
    "ScopeLookupPoint",
    "TargetScope",
    "definition_shape",
    "macro_source_from_head",
    "line_marker_of",
    "make_shape",
    "parse",
    "signature_of",
]
