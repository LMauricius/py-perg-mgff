"""MGFF's chain of phases read as ANTLR's two.

An ANTLR grammar has exactly two stages and they are fixed: a lexer that reads
characters and a parser that reads the tokens it produced. MGFF's chain is open
— a grammar names its own phases and says which follows which — so the whole of
this module is the narrowing of one onto the other, and the reporting of a
grammar that does not fit.

**Which production is a token** is the question this answers that nothing else
can. MGFF has two established ways of saying it, and both are honoured, because
both are written in the wild:

    d Int = ( Digit )+          d Number = ( 0-9 )+
          > token                        > class(Number) push(tokens)

The first is the calculator of the specification's Appendix A; the second is what
a phase reading `over(tokens)` needs anyway. A lexer production that says neither
is a **fragment**: it exists to be spelled into the rules that call it, which is
exactly what `fragment` means in ANTLR.

The lists a match is pushed to carry across too. The one the parser reads is the
token stream itself and needs no saying; any other becomes an ANTLR **channel**,
which is the same idea — a match that reaches the output without reaching the
parser.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ...diagnostics.errors import GeneratorError
from ...mgff.systems.model import GrammarModel, Production, Target
from ..utils.pipeline import (
    FINAL_TARGET,
    rewrite_terminals_as_calls,
    target_stage_chain_of,
)
from ..utils.streams import pushed_list_names_of, stored_field_of

#: The attribute a grammar writes on a lexer production that is a token in its
#: own right, rather than a piece one is spelled out of.
TOKEN_ATTRIBUTE = "token"


def is_skipped(production: Production) -> bool:
    """Whether a production's match is thrown away rather than handed on.

    `> skip` says so; `> skip(false)` says the opposite, and is how a grammar
    opts one production out of a shared attribute list that skips.
    """
    if "skip" not in production.attributes:
        return False
    values = production.attributes["skip"]
    return not values or values[0].lower() != "false"


@dataclass(slots=True)
class AntlrPhases:
    """The grammar as ANTLR's lexer and parser, and what each production is."""

    lexer: Target
    parser: Target
    #: The list the parser reads, from `> over(…)`, or None when the parser
    #: phase re-reads the text and its terminals are literals.
    read_list: str | None
    lexer_rules: dict[str, Production] = field(default_factory=dict)
    parser_rules: dict[str, Production] = field(default_factory=dict)
    #: The lexer rules that are tokens; every other one is a fragment.
    tokens: set[str] = field(default_factory=set)
    #: The channel each lexer production writes to, where it is not the default.
    channels: dict[str, str] = field(default_factory=dict)

    def is_fragment(self, name: str) -> bool:
        """Whether a lexer rule is a piece rather than a token of its own."""
        return name in self.lexer_rules and name not in self.tokens

    def label_of(self, name: str) -> tuple[str, str] | None:
        """The label a reference to a production carries, as (name, operator).

        `store(f)` gives `f=`, and `push(l)` gives `l+=`, which are ANTLR's two
        label operators for a field holding one match and a field holding many.
        Pushing to the list the parser reads is the phase's own plumbing and
        names no field, and a *lexer* production's push is a channel rather than
        a field — see `_channels` — so only a parser rule's is read here.
        """
        production = self.parser_rules.get(name) or self.lexer_rules.get(name)
        if production is None:
            return None
        if "store" in production.attributes:
            field_name = stored_field_of(production)
            if field_name is not None:
                return field_name, "="
        if name in self.parser_rules:
            for list_name in pushed_list_names_of(production):
                if list_name != self.read_list:
                    return list_name, "+="
        return None


# -- reading the chain -------------------------------------------------------


def read_phases(model: GrammarModel) -> AntlrPhases:
    """The grammar as ANTLR's two phases, or a report of why it is not two.

    The chain itself is read by `utils.pipeline`, which already reports every way
    one can be malformed; what is added here is ANTLR's own requirement that
    there be a lexer and a parser and nothing else.
    """
    stages = target_stage_chain_of(model)
    if len(stages) != 2:
        listed = ", ".join(repr(stage.target.name) for stage in stages)
        raise GeneratorError(
            f"an ANTLR grammar has two phases, a lexer and a parser, and this "
            f"grammar has {len(stages)}: {listed}. Write one `t Lex ( … )` phase "
            f"for the tokens and `> post(Lex)` on {FINAL_TARGET!r} for the rules."
        )
    lexer_stage, parser_stage = stages

    # A parser phase reading a list matches classes rather than characters, and
    # this is what turns those terminals into calls on the tokens carrying them.
    rewrite_terminals_as_calls(parser_stage)

    # The lexer's table already holds every shared macro it reached, so what is
    # left of the parser's table is the parser's own.
    lexer_rules = dict(lexer_stage.target.productions)
    parser_rules = {
        name: production
        for name, production in parser_stage.target.productions.items()
        if name not in lexer_rules
    }

    phases = AntlrPhases(
        lexer=lexer_stage.target,
        parser=parser_stage.target,
        read_list=parser_stage.over,
        lexer_rules=lexer_rules,
        parser_rules=parser_rules,
    )
    phases.tokens = _token_names(phases)
    phases.channels = _channels(phases)
    return phases


def _token_names(phases: AntlrPhases) -> set[str]:
    """The lexer productions that are tokens rather than fragments."""
    found = {
        name
        for name, production in phases.lexer_rules.items()
        if TOKEN_ATTRIBUTE in production.attributes
        or (phases.read_list is not None and phases.read_list in pushed_list_names_of(production))
    }
    if not found:
        said = (
            f"`> push({phases.read_list})`"
            if phases.read_list is not None
            else f"`> {TOKEN_ATTRIBUTE}`"
        )
        raise GeneratorError(
            f"no production of phase {phases.lexer.name!r} is a token, so the "
            f"parser would have nothing to read. Write {said} on each one that is."
        )
    return found


def _channels(phases: AntlrPhases) -> dict[str, str]:
    """The channel each lexer production writes to, where it is not the default.

    The list the parser reads is the default channel and is not named again. One
    other list is a channel of its own; two are not expressible, since a token
    reaches exactly one channel.
    """
    found: dict[str, str] = {}
    for name, production in phases.lexer_rules.items():
        others = [
            list_name
            for list_name in pushed_list_names_of(production)
            if list_name != phases.read_list
        ]
        if not others:
            continue
        if len(others) > 1:
            listed = ", ".join(repr(one) for one in others)
            raise GeneratorError(
                f"{name!r} is pushed to {listed}; an ANTLR token reaches one "
                "channel, so it may name at most one list besides the one the "
                "parser reads"
            )
        if is_skipped(production):
            raise GeneratorError(
                f"{name!r} is both skipped and pushed to {others[0]!r}; a skipped "
                "match reaches no channel at all, so it can be one or the other"
            )
        found[name] = others[0]
    return found
