"""A backend writing an ANTLR 4 grammar.

The output is one combined `.g4` file — `grammar Name;`, then the parser rules in
lower case and the lexer rules in upper — which is the arrangement ANTLR's own
tooling expects and the closest thing it has to MGFF's pair of phases. See
`Docs/antlr-generator.md`.

Most of MGFF maps across without loss, and where it does the backend says so
plainly rather than approximating:

- **The phases are ANTLR's.** The first phase is the lexer, `Parse` is the
  parser, and a grammar with any other number of phases is reported. `phases`
  decides which production is a token, which a fragment, and which reaches a
  channel of its own.
- **Left recursion is kept where ANTLR takes it.** A directly left-recursive rule
  is written as it stands, since ANTLR reads it and derives precedence from the
  order of its alternatives. Only an indirect cycle, which ANTLR refuses, is
  rewritten — see `recursion`.
- **Parametrized macros are already gone.** `resolve` spells a call carrying
  arguments out where it is written, so nothing here has to flatten anything:
  what arrives is a rule tree of plain references.
"""

from __future__ import annotations

from pathlib import Path

from ...diagnostics.errors import GeneratorError
from ...mgff.systems.model import GrammarModel, Production
from ..base import Generator
from ..utils.emit import Emitter
from ..utils.highlight import START_PRODUCTION
from ..utils.naming import pascal_case, safe_file_name, safe_identifier
from ..utils.settings import setting_value
from .phases import AntlrPhases, is_skipped, read_phases
from .recursion import rewrite_indirect_left_recursion
from .rules import RuleNames, RuleWriter


def _section(title: str) -> str:
    """A banner comment introducing one part of the file."""
    return f"// -- {title} ".ljust(72, "-")


#: The one channel besides the default that a combined grammar has. ANTLR
#: declares custom channels in a `channels { … }` block, which only a `lexer
#: grammar` may carry, so a single file has this one to give away.
HIDDEN_CHANNEL = "HIDDEN"


def _start_first(names: list[str]) -> list[str]:
    """The productions in written order, with the starting one at their head.

    A `.g4` file names no start rule, so the one a reader should begin at is put
    where a reader begins. `File` is the same name every other backend starts at.
    """
    if START_PRODUCTION not in names:
        return names
    return [START_PRODUCTION] + [name for name in names if name != START_PRODUCTION]


class AntlrGenerator(Generator):
    """Writes one combined `.g4` grammar holding the lexer and the parser."""

    name = "antlr"
    description = "write one combined ANTLR 4 grammar"

    def generate(self, model: GrammarModel, out_dir: Path) -> list[Path]:
        out_dir.mkdir(parents=True, exist_ok=True)
        # ANTLR requires the file to be named after the grammar inside it.
        path = out_dir / f"{safe_file_name(self.grammar_name(model), 'Grammar')}.g4"
        # `Emitter.render` already ends the last line.
        path.write_text(self.render(model), encoding="utf-8")
        return [path]

    def grammar_name(self, model: GrammarModel) -> str:
        """What the grammar calls itself: `> name(…)`, else the file's own name."""
        written = setting_value(model.attributes, "name")
        wanted = written or pascal_case(Path(model.name).stem)
        return safe_identifier(wanted, fallback="Grammar")

    # -- the grammar -------------------------------------------------------

    def render(self, model: GrammarModel) -> str:
        """The whole grammar as one file, without touching the file system."""
        phases = read_phases(model)
        rewrite_indirect_left_recursion(phases.parser_rules)
        names = RuleNames(phases)
        writer = RuleWriter(phases, names)

        self._check_one_channel(phases)

        out = Emitter()
        out.write_line(f"grammar {self.grammar_name(model)};")
        self._write_parser(out, phases, names, writer)
        self._write_lexer(out, phases, names, writer)
        return out.render()

    def _check_one_channel(self, phases: AntlrPhases) -> None:
        """One file holds one channel besides the default, so only one list may ask."""
        wanted = sorted(set(phases.channels.values()))
        if len(wanted) > 1:
            listed = ", ".join(repr(one) for one in wanted)
            raise GeneratorError(
                f"the lexer pushes to {listed} besides the list the parser reads, "
                f"and one grammar file has one channel — {HIDDEN_CHANNEL} — to "
                "give them; push what is kept but not parsed to a single list"
            )

    def _write_parser(
        self, out: Emitter, phases: AntlrPhases, names: RuleNames, writer: RuleWriter
    ) -> None:
        out.write_line()
        out.write_line(_section(phases.parser.name))
        for name in _start_first(list(phases.parser_rules)):
            out.write_line()
            self._write_rule(
                out, names.of(name), phases.parser_rules[name], writer, in_lexer=False
            )

    def _write_lexer(
        self, out: Emitter, phases: AntlrPhases, names: RuleNames, writer: RuleWriter
    ) -> None:
        # Tokens come first and keep their written order: ANTLR breaks a tie
        # between two rules matching the same length by which was written first.
        tokens = [name for name in phases.lexer_rules if name in phases.tokens]
        fragments = [name for name in phases.lexer_rules if name not in phases.tokens]

        out.write_line()
        out.write_line(_section(phases.lexer.name))
        for name in tokens:
            out.write_line()
            self._write_rule(
                out,
                names.of(name),
                phases.lexer_rules[name],
                writer,
                in_lexer=True,
                commands=self._commands(phases, name),
            )
        if not fragments:
            return
        out.write_line()
        out.write_line(_section("fragments"))
        for name in fragments:
            out.write_line()
            self._write_rule(
                out, names.of(name), phases.lexer_rules[name], writer, in_lexer=True,
                prefix="fragment ",
            )

    def _commands(self, phases: AntlrPhases, name: str) -> list[str]:
        """What a token rule does with its match besides handing it on."""
        production = phases.lexer_rules[name]
        if is_skipped(production):
            return ["skip"]
        if name in phases.channels:
            return [f"channel({HIDDEN_CHANNEL})"]
        return []

    def _write_rule(
        self,
        out: Emitter,
        written_name: str,
        production: Production,
        writer: RuleWriter,
        in_lexer: bool,
        commands: list[str] | None = None,
        prefix: str = "",
    ) -> None:
        """One rule, over as many lines as its alternatives need."""
        alternatives = writer.alternatives(production, in_lexer)
        tail = f" -> {', '.join(commands)}" if commands else ""
        # A command belongs to an alternative rather than to the rule, so a rule
        # carrying one is written as the single alternative its options make up.
        if tail and len(alternatives) > 1:
            alternatives = ["( " + " | ".join(alternatives) + " )"]

        if len(alternatives) == 1:
            out.write_line(f"{prefix}{written_name} : {alternatives[0]}{tail} ;")
            return
        out.write_line(f"{prefix}{written_name}")
        with out.indented():
            out.write_line(f": {alternatives[0]}")
            for alternative in alternatives[1:]:
                out.write_line(f"| {alternative}")
            out.write_line(";")
