"""The chain of phases a grammar generates, and what each one reads.

MGFF names no phase and fixes no order between them: a target is a scope with a
name, and which target follows which is a decision the grammar makes and a
generator reads. Two attributes on a target say it:

    t Parse (
        > post(Lex) over(tokens)

`post(Other)` puts this phase after `Other`. `over(list)` says it matches the
list `Other` filled with `push(list)`, rather than text. A phase with no `post`
is the first, and it always reads text — a grammar of a language starts at
characters, and there is nothing before them to read. The chain ends at `Parse`,
which is the one phase every backend of this kind requires.

**What `over` changes is what a terminal means.** In a phase reading text, `\\(`
is the character. In a phase reading a list of matches, it is *the match whose
class is `(`* — so the phase before it says

    d LParen = \\(
             > class(\\() style(Normal) push(tokens)

and the phase after it goes on writing `\\( Expr \\)`, meaning the token now. That
rewriting is done here, once, by replacing such a terminal with a reference to
the production that produces it; everything downstream then reads an ordinary
rule tree and needs to know nothing about phases.

A grammar whose later phase re-reads characters simply leaves `over` off. That is
not a lesser arrangement: a syntax highlighter for MGFF itself does exactly that,
because what it highlights is where a line's marker sits, not which tokens the
line holds.
"""

from __future__ import annotations

from dataclasses import dataclass

from ...diagnostics.errors import GeneratorError
from ...mgff.common.characters import character_set_matched_by
from ...mgff.common.rules import Choice, Reference, Rule
from ...mgff.lexing.escapes import escape_character
from ...mgff.semantics.model import GrammarModel, Production, Target
from .classes import match_classes_of
from .settings import setting_value
from .streams import pushed_list_names_of
from .walk import referenced_production_names, rewrite_rule_tree

#: The phase every backend reading a chain of them ends at.
FINAL_TARGET = "Parse"


@dataclass(slots=True)
class HighlightStage:
    """One phase of the chain, and what it reads."""

    target: Target
    #: The phase before this one, None for the one that reads text.
    previous: "HighlightStage | None" = None
    #: The list this phase matches over, None when it matches characters.
    over: str | None = None

    @property
    def matches_characters(self) -> bool:
        """Whether the phase reads text rather than a list of earlier matches."""
        return self.over is None


# -- building the chain ------------------------------------------------------


def highlight_stages_of(model: GrammarModel) -> list[HighlightStage]:
    """Every phase of the grammar, first to last, ending at `Parse`.

    Raises `GeneratorError` on a chain that is no chain: a `post` naming a target
    that is not there, two phases claiming the same predecessor, a cycle, more
    than one phase that starts from text, or a target left out of the chain
    altogether. A grammar of a single target needs no attributes at all.
    """
    if not model.targets:
        raise GeneratorError(
            "this grammar defines no target; a phase is written "
            "`t Name ( … )`, and the last one is called `Parse`"
        )

    order = _targets_in_phase_order(model)
    stages: list[HighlightStage] = []
    for target in order:
        over = setting_value(target.attributes, "over")
        previous = stages[-1] if stages else None
        if over is not None and previous is None:
            raise GeneratorError(
                f"target {target.name!r} is `over({over})` but runs first, and the "
                "first phase reads the text itself; drop `over`, or give it a "
                "`post(…)` naming the phase that fills that list"
            )
        stages.append(HighlightStage(target=target, previous=previous, over=over))

    if stages[-1].target.name != FINAL_TARGET:
        raise GeneratorError(
            f"the last phase is {stages[-1].target.name!r}; it has to be "
            f"{FINAL_TARGET!r}, which is where generation ends. Write "
            f"`> post({stages[-1].target.name})` on {FINAL_TARGET!r}."
        )
    return stages


def _targets_in_phase_order(model: GrammarModel) -> list[Target]:
    """The targets ordered by their `post` attributes, first to last."""
    by_name = {target.name: target for target in model.targets}
    # Who each target follows, and — read the other way — who follows it.
    follows: dict[str, str] = {}
    for target in model.targets:
        after = setting_value(target.attributes, "post")
        if after is None:
            continue
        if after not in by_name:
            raise GeneratorError(
                f"target {target.name!r} is `post({after})`, and this grammar has "
                f"no target called {after!r}"
            )
        if after == target.name:
            raise GeneratorError(f"target {target.name!r} runs after itself")
        follows[target.name] = after

    firsts = [name for name in by_name if name not in follows]
    if not firsts:
        raise GeneratorError(
            "every phase runs after another, so the chain has no beginning; "
            "the phase that reads the text carries no `post(…)`"
        )
    if len(firsts) > 1:
        listed = ", ".join(repr(name) for name in sorted(firsts))
        raise GeneratorError(
            f"the phases {listed} all run first; exactly one does, and every "
            "other names the phase it runs after with `post(…)`"
        )

    next_of: dict[str, str] = {}
    for name, after in follows.items():
        if after in next_of:
            raise GeneratorError(
                f"targets {next_of[after]!r} and {name!r} both run after "
                f"{after!r}; the phases are a chain, not a tree"
            )
        next_of[after] = name

    ordered: list[Target] = []
    name: str | None = firsts[0]
    while name is not None:
        ordered.append(by_name[name])
        name = next_of.get(name)
    if len(ordered) != len(by_name):
        on_chain = {target.name for target in ordered}
        left = ", ".join(repr(one) for one in by_name if one not in on_chain)
        raise GeneratorError(
            f"the phases {left} are not on the chain that ends at "
            f"{FINAL_TARGET!r}; they would never run"
        )
    return ordered


def all_productions_of_stages(stages: list[HighlightStage]) -> dict[str, Production]:
    """Every phase's productions in one table, later phases winning a clash.

    A phase reaching back into an earlier one resolves the name there, so the
    expressions of both are needed together; where two phases define the same
    name, the later one is the one being generated.
    """
    merged: dict[str, Production] = {}
    for stage in stages:
        merged.update(stage.target.productions)
    return merged


# -- matching a list of earlier matches --------------------------------------


def productions_pushing_to(stage: HighlightStage, list_name: str) -> list[Production]:
    """The previous phase's productions that append themselves to a list."""
    if stage.previous is None:
        return []
    return [
        production
        for production in stage.previous.target.productions.values()
        if list_name in pushed_list_names_of(production)
    ]


def rewrite_terminals_as_calls(stage: HighlightStage) -> None:
    """Rewrite a phase's terminals as calls on the matches they name.

    Only a phase with `over(…)` has anything to do here. Every terminal of it is
    a class of the list it reads, so `\\(` becomes a call on whichever production
    carries `class(\\()`; several carrying it become a choice, and none is an
    error, which is what catches a class misspelled on either side.

    Only the productions *written in* this phase are rewritten. A phase reaching
    back by name — `d Skipped = Space / Comment` — pulls the earlier phase's
    productions into its own table, and those still match the text they always
    did; rewriting them would read their own character sets as classes.

    The productions reached by class are copied into this phase's table, since
    they are now referenced from it, and so is everything they reach in turn.
    """
    if stage.over is None or stage.previous is None:
        return

    by_class = _productions_by_class(stage, stage.over)
    reached: set[str] = set()

    def replace(node: Rule) -> Rule | None:
        characters = character_set_matched_by(node)
        if characters is None:
            return None
        character = characters.single_character
        if character is None:
            raise GeneratorError(
                f"target {stage.target.name!r} matches over {stage.over!r} rather "
                "than over text, so a set of characters names nothing there; "
                "write the classes of the matches you mean"
            )
        # A class is the text it was written as, so a character is looked up by
        # the way MGFF spells it: the class of `\(` is written `\(`, since a
        # bare bracket would open a group.
        written = escape_character(character)
        found = by_class.get(written) or by_class.get(character)
        if not found:
            raise GeneratorError(
                f"target {stage.target.name!r} matches {written}, and nothing "
                f"pushed to {stage.over!r} carries that class. Write "
                f"`> class({written}) push({stage.over})` on the match that "
                "produces it."
            )
        reached.update(found)
        if len(found) == 1:
            return Reference(found[0])
        return Choice([Reference(name) for name in found], "/")

    for production in list(stage.target.productions.values()):
        if production.origin != stage.target.name:
            continue
        production.alternatives = [
            rewrite_rule_tree(alternative, replace) for alternative in production.alternatives
        ]
    _copy_reached_productions(stage, reached)


def _productions_by_class(stage: HighlightStage, list_name: str) -> dict[str, list[str]]:
    """Which productions of the previous phase answer to each class."""
    found: dict[str, list[str]] = {}
    for production in productions_pushing_to(stage, list_name):
        for name in match_classes_of(production):
            found.setdefault(name, []).append(production.name)
    return found


def _copy_reached_productions(stage: HighlightStage, names: set[str]) -> None:
    """Copy productions of the previous phase into this one, with what they reach."""
    assert stage.previous is not None
    source = stage.previous.target.productions
    pending = list(names)
    while pending:
        name = pending.pop()
        if name in stage.target.productions or name not in source:
            continue
        production = source[name]
        stage.target.productions[name] = production
        pending.extend(referenced_production_names(production.rule))
