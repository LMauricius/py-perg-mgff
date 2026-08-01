"""Name resolution across targets, prefixes and parameters (Part 2).

Not implemented yet.

A call resolves to what is visible where it is written: a macro, or a parameter
of an enclosing macro. Prefixes concatenate, and a macro inside a prefix may be
called by its local name from within and by its full name from without. Macros
defined outside every target and prefix are visible to all targets.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..grammar.scope import Macro, Scope


@dataclass(slots=True)
class SymbolTable:
    """The macros visible at one point, together with the enclosing tables."""

    parent: SymbolTable | None = None
    macros: dict[str, Macro] = field(default_factory=dict)
    parameters: dict[str, object] = field(default_factory=dict)

    def lookup(self, name: str, argument_count: int) -> Macro | None:
        """Find a macro or parameter by name, innermost scope first."""
        raise NotImplementedError


def build(scope: Scope) -> SymbolTable:
    """Build the symbol table of a scope tree, applying the prefixes."""
    # 1. Collect the macros defined directly in this scope under their prefixed names.
    # 2. Recurse into the children, chaining their tables to this one.
    # 3. Report duplicate definitions as semantic errors.
    raise NotImplementedError


def target_visibility(root: Scope, target: str) -> SymbolTable:
    """The names one target may call.

    Whether a later target may call an earlier target's macros is a decision of
    the generator, not of MGFF, so the backend supplies the policy.
    """
    raise NotImplementedError
