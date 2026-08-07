"""A backend writing one regular expression.

The grammar is read from the macro named `Match`, and the output is the pattern
that matches it — the PCRE dialect `utils.regex` writes, which Python's `regex`
module, PHP, Perl and Qt all read. See `Docs/regex-generator.md`.

Three things set this backend apart from the others:

- **No targets.** A regular expression is one pass over the text, so there is
  nothing for `Lex` and `Parse` to be. The grammar is written at file scope, and
  a target is reported rather than quietly flattened.
- **Capture groups come from `store`.** A production carrying `> store(name)`
  becomes `(?P<name>…)` wherever it is called, so what is captured is a property
  of the rule rather than of the place it was used.
- **Only regular grammars.** MGFF describes far more than a regular expression
  can match. What can be rescued is rescued — a production that calls itself at
  the start or the end of an alternative is a repetition in disguise, and
  `linear` solves it — and what cannot is reported, naming the productions at
  fault.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path

from ...diagnostics.errors import GeneratorError
from ...mgff.common.rules import Rule
from ...mgff.semantics.model import GrammarModel, Production
from ..base import Generator
from ..utils.regex import regex_of
from ..utils.streams import pushed_list_names_of, stored_field_of
from .linear import patterns_for_all_productions

#: The macro a grammar is read from.
START = "Match"

#: A capture group in the output, for the duplicate-name check.
GROUP_NAME = re.compile(r"\(\?P<([^>]*)>")


def _duplicate_capture_names(pattern: str) -> list[str]:
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

    def __init__(self) -> None:
        #: The table `productions_to_read` settled, for `wrapped_in_capture_group` to look a name up in.
        self.productions: dict[str, Production] = {}

    def generate(self, model: GrammarModel, out_dir: Path) -> list[Path]:
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"{Path(model.name).stem}.regex"
        path.write_text(self.render(model) + "\n", encoding="utf-8")
        return [path]

    # -- the pattern -------------------------------------------------------

    def render(self, model: GrammarModel) -> str:
        """The whole grammar as one pattern, without touching the file system."""
        productions = self.productions_to_read(model)
        pattern = patterns_for_all_productions(
            productions, START, self.render_rule, self.wrapped_in_capture_group
        )[START]

        # A capture group inside a production reached twice is written twice, and
        # a name may only be used once in a pattern.
        duplicates = _duplicate_capture_names(pattern)
        if duplicates:
            listed = ", ".join(repr(name) for name in duplicates)
            raise GeneratorError(
                f"the capture group {listed} would appear more than once in the "
                "expression, which no engine allows; a production carrying "
                "`store` is written out wherever it is called, so a stored "
                "production may only be reached once"
            )
        return pattern

    def productions_to_read(self, model: GrammarModel) -> dict[str, Production]:
        """The productions to read, checking that the grammar has the shape for it."""
        if model.targets:
            listed = ", ".join(repr(target.name) for target in model.targets)
            raise GeneratorError(
                f"this grammar defines the target(s) {listed}; a regular expression "
                "is one pass over the text and has no phases, so write the macros "
                "at file scope instead"
            )
        productions = model.globals.productions
        # Kept for `wrapped_in_capture_group`, which is asked about a production by name alone.
        self.productions = productions
        if START not in productions:
            raise GeneratorError(
                f"this grammar defines no macro named {START!r}, which is where "
                "the expression starts"
            )
        return productions

    # -- one rule ----------------------------------------------------------

    def wrapped_in_capture_group(self, name: str, pattern: str) -> str:
        """A stored production as the named group every call of it becomes.

        `push` has no counterpart here: one expression matches once and produces
        one result, so there is no list for a match to be appended to.
        """
        production = self.productions[name]
        if pushed_list_names_of(production):
            raise GeneratorError(
                f"`push` on {name!r} has no meaning in one expression, which "
                "matches once and produces one result; use `store` instead"
            )
        field = stored_field_of(production)
        return pattern if field is None else f"(?P<{field}>{pattern})"

    def render_rule(self, node: Rule, patterns: Mapping[str, str]) -> str:
        """One rule as a pattern, with the productions it calls already solved."""
        pattern = regex_of(
            node, find_production=_no_inlining, emit_macro_call=None, patterns=patterns
        )
        if pattern is None:
            raise GeneratorError(
                "this rule has no regular form: it calls something a regular "
                "expression cannot express"
            )
        return pattern


def _no_inlining(name: str) -> Production | None:
    """Every reference is answered by a solved pattern, so none is inlined here."""
    return None
