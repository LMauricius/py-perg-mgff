"""A backend writing one regular expression.

The grammar is read from the macro named `Match`, and the output is the pattern
that matches it — the PCRE dialect `utils.regex` writes, which Python's `regex`
module, PHP, Perl and Qt all read. See `Docs/regex-generator.md`.

Two things set this backend apart from the others:

- **No targets.** A regular expression is one pass over the text, so there is
  nothing for `Lex` and `Parse` to be. The grammar is written at file scope, and
  a target is reported rather than quietly flattened.
- **Only regular grammars.** MGFF describes far more than a regular expression
  can match. What can be rescued is rescued — a production that calls itself at
  the start or the end of an alternative is a repetition in disguise, and
  `linear` solves it — and what cannot is reported, naming the productions at
  fault.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from pathlib import Path

from ...diagnostics.errors import GeneratorError
from ...mgff.common.rules import MacroCall, Rule
from ...mgff.grammar.macros import MacroDefinition
from ...mgff.semantics.model import GrammarModel, Production
from ..base import Generator
from ..utils.regex import regex_of
from .captures import CAPTURE, VALID_NAME, capture_name, is_capture
from .linear import patterns_for

#: The macro a grammar is read from.
START = "Match"

#: A capture group in the output, for the duplicate-name check.
GROUP_NAME = re.compile(r"\(\?P<([^>]*)>")


def _duplicate_names(pattern: str) -> list[str]:
    """The capture names appearing more than once, in the order they first do."""
    seen: set[str] = set()
    repeated: list[str] = []
    for name in GROUP_NAME.findall(pattern):
        if name in seen and name not in repeated:
            repeated.append(name)
        seen.add(name)
    return repeated


class RegexGenerator(Generator):
    """Writes one `.regex` file holding the pattern the grammar describes."""

    name = "regex"
    description = "write one regular expression, starting from the `Match` macro"

    def extra_macros(self) -> list[MacroDefinition]:
        return [CAPTURE]

    def generate(self, model: GrammarModel, out_dir: Path) -> list[Path]:
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"{Path(model.name).stem}.regex"
        path.write_text(self.render(model) + "\n", encoding="utf-8")
        return [path]

    # -- the pattern -------------------------------------------------------

    def render(self, model: GrammarModel) -> str:
        """The whole grammar as one pattern, without touching the file system."""
        productions = self.productions_of(model)
        pattern = patterns_for(productions, START, self.render_rule)[START]

        # A capture group inside a production reached twice is written twice, and
        # a name may only be used once in a pattern.
        duplicates = _duplicate_names(pattern)
        if duplicates:
            listed = ", ".join(repr(name) for name in duplicates)
            raise GeneratorError(
                f"the capture group {listed} would appear more than once in the "
                "expression, which no engine allows; a group inside a production "
                "that is used twice is written twice, so name it once or leave it "
                "unnamed"
            )
        return pattern

    def productions_of(self, model: GrammarModel) -> dict[str, Production]:
        """The productions to read, checking that the grammar has the shape for it."""
        if model.targets:
            listed = ", ".join(repr(target.name) for target in model.targets)
            raise GeneratorError(
                f"this grammar defines the target(s) {listed}; a regular expression "
                "is one pass over the text and has no phases, so write the macros "
                "at file scope instead"
            )
        productions = model.globals.productions
        if START not in productions:
            raise GeneratorError(
                f"this grammar defines no macro named {START!r}, which is where "
                "the expression starts"
            )
        return productions

    # -- one rule ----------------------------------------------------------

    def render_rule(self, node: Rule, patterns: Mapping[str, str]) -> str:
        """One rule as a pattern, with the productions it calls already solved."""
        pattern = regex_of(node, lookup=_nothing, emit=self.emit, patterns=patterns)
        if pattern is None:
            raise GeneratorError(
                "this rule has no regular form: it calls something a regular "
                "expression cannot express"
            )
        return pattern

    def emit(self, node: MacroCall, inner: Callable[[Rule], str | None]) -> str | None:
        """A capture group, which is the one macro this backend adds."""
        if not is_capture(node):
            return None
        body = inner(node.arguments[0])
        if body is None:
            return None
        name = capture_name(node)
        if not name:
            return f"({body})"
        if not VALID_NAME.fullmatch(name):
            raise GeneratorError(
                f"{name!r} is no name for a capture group; a name is a letter or "
                "an underscore followed by letters, digits or underscores"
            )
        return f"(?P<{name}>{body})"


def _nothing(name: str) -> Production | None:
    """Every reference is answered by a solved pattern, so none is inlined here."""
    return None
