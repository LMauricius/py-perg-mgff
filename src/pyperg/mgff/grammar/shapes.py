"""What a macro shape is: the name-pattern a call may be recognised by.

MGFF has one kind of item — a call — and a macro is whatever answers to it. A
macro's *name* is therefore a pattern rather than a fixed string: the pattern is
matched against the item's **signature**, its text with the groups emptied, so
`( Digit )+` gives `()+` and `sep(x)by(y)` gives `sep()by()`.

A shape is two things, and both are generic:

    pattern            which calls it answers to
    extract_arguments  what such a call carries, as a dictionary

The dictionary is the shape's whole meaning. What a call then *produces* is the
business of the `MacroDefinition` holding the shape.

This module is the definition and nothing else. The shapes actually recognised
are built in `signatures` — the one a grammar's own `d` lines answer to — and in
`mgff.common`, which is the vocabulary a rule-tree backend starts with.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from ..lexing.cst import Item

#: Reads a matched call: the item, and the match of its shape's pattern. The
#: keys of the result are the parameter names a `produce_call` is written with.
ExtractArguments = Callable[[Item, re.Match[str]], dict[str, object]]


@dataclass(frozen=True, slots=True)
class MacroShape:
    """A name-pattern, and what a call of it carries."""

    name: str  # what the shape is called, in messages and dumps
    pattern: re.Pattern[str]
    extract_arguments: ExtractArguments

    def match(self, signature: str) -> re.Match[str] | None:
        """Whether a signature calls this shape, and what its pattern captured."""
        return self.pattern.fullmatch(signature)
