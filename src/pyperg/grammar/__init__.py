"""Grammar semantics (specification Part 2): what the lines of a file mean.

The reading of a lexed file into scopes, targets and macros lives here; the
lexical structure it starts from is `pyperg.mgff`.
"""

from .parser import marker_of, parse
from .scope import Macro, Scope, Target, make_macro, signature_of

__all__ = ["Macro", "Scope", "Target", "make_macro", "marker_of", "parse", "signature_of"]
