"""A backend writing one HTML file per each production.

The grammar is read without a starting macro, and written to human-readable HTML text.
It uses a smart-ish transform of language matching rules into a number
of partially-expanded code snippets, with styled HTML marks above the code.
The partial expansion tries to not go too deep, so it will reference more complex constructs
instead of expanding them.

Three things set this backend apart from the others:

- **No special handling of targets or parsing logic.** The productions are read as separate units,
  with their references and structures read just enough to execute partial expansion of macros.
- **html(...) macro attribute.** Each macro can define a custom HTML snippet
  that it will be turned into by this generator. Macros with arguments can reference
  their arguments inside the html() attribute, in which case the arguments will be transformed
  into HTML too, rather than expanded into match rules.
  If a macro doesn't have a html() attribute, the parametrized macros will be left as-is,
  while those without arguments will be replaced by their expansion.
- **A large number of output files.** The files will be written to the output directory.
  One file per each macro without arguments.
  The files are named as <TARGET>_<PREFIXES>_<PRODUCTION NAME>.html.
"""

from __future__ import annotations
from typing import Iterable, Iterator

from collections.abc import Mapping
from pathlib import Path

from ...diagnostics.errors import GeneratorError
from ...mgff.common.rules import Rule
from ...mgff.systems.grammar import GrammarModel, Production
from ...mgff.systems.grammar import GrammarTarget
from ..base import Generator


class HtmlGenerator(Generator):
    """Writes a HTML file per each production the grammar describes."""

    name = "html"
    description = "write a HTML file describing each production"

    def __init__(self) -> None:
        #: The table `productions_to_read` settled, for `wrapped_in_capture_group` to look a name up in.
        self.productions: dict[str, Production] = {}

    def generate(self, model: GrammarModel, out_dir: Path) -> Iterable[Path]:
        for prodpath, prod in self.iterate([model.globals] + model.targets):
            path = out_dir / f"{prodpath}.html"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(self.render(prod, model) + "\n", encoding="utf-8")
            yield path

    # -- the pattern -------------------------------------------------------

    def iterate(
        self, targets: Iterable[GrammarTarget]
    ) -> Iterator[tuple[str, Production]]:
        """
        Iterates over (name, prod) tuples,
        for all non-parametrized productions in all targets and prefixes.
        The target and prefix structure is separated by '/' in the name
        """
        # for t in targets:
        #    for subt in t.
        # for p in model.target:
        yield (Path(), Production())

    def render(self, prod: Production, model: GrammarModel) -> str:
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
