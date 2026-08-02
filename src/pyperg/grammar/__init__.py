"""Grammar semantics (specification Part 2): what the lines of a file mean.

The reading of a lexed file into scopes, targets and macros lives here; the
lexical structure it starts from is `pyperg.mgff`.
"""

from .macros import MacroDefinition
from .parser import marker_of, parse
from .scope import MacroSource, Scope, Target, make_source, signature_of

__all__ = [
    "MacroDefinition",
    "MacroSource",
    "Scope",
    "Target",
    "make_source",
    "marker_of",
    "parse",
    "signature_of",
]
