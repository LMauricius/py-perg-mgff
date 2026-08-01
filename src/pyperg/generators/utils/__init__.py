"""Helpers shared by the generator backends.

Nothing here knows about a particular output language. A backend imports what it
needs; the front end never imports from this package, so the dependency runs one
way only.

    walk      reading and rewriting rule trees
    graph     the reference graph: reachability, recursion, ordering
    regex     rule trees and character sets as regular expressions
    naming    collision-free names for generated symbols
    emit      an indent-aware line writer
    xmlwrite  a small XML element builder
"""

from .emit import Emitter
from .naming import NameAllocator
from .xmlwrite import Element, escape_attribute, escape_text

__all__ = ["Element", "Emitter", "NameAllocator", "escape_attribute", "escape_text"]
