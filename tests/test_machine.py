"""The highlighting machine: what may appear where, derived from `Parse`."""

from pathlib import Path

import pytest

from pyperg.generators.kate import KateGenerator
from pyperg.generators.utils.highlight import token_order
from pyperg.generators.utils.machine import (
    INLINE,
    POP,
    SPAN,
    STAY,
    TOKEN,
    Classifier,
    MachineBuilder,
)
from pyperg.generators.utils.regex import regex_of
from pyperg.mgff.lexing.lexer import lex_text
from pyperg.mgff.semantics.model import resolve

MGFF = Path(__file__).parent.parent / "examples" / "mgff-new.mgff"

# A grammar of line roles: a marker opens a line, a group holds items and
# nothing else, and a comment reaches past its line through a group.
LINES = """
t Lex (
    d Marker = d
        > class(Keyword)
    d Hash = #
        > class(Comment)
    d Name = ( a-z|A-Z )+
    d Space = ( \\_ )+
    d NewLine = \\n
    d File = ( (Marker)/(Hash)/(Name)/(Space) )*
)

t Parse (
    d Items = ( (Name)/(Group)/(Space) )*
    d Group = \\( Items \\)
    d Definition = Marker Items NewLine
    d Comment = Hash Items NewLine
        > class(Comment)
    d Line = (Definition)/(Comment)
    d File = ( (Line)/(NewLine) )*
)
"""


def machine_of(text: str, name: str = "<test>"):
    model = resolve(lex_text(text, name), name, KateGenerator().macros())
    parse = model.target("Parse")
    lex = model.target("Lex")
    return MachineBuilder(parse, token_order(lex) if lex else []).build(), parse


def context_of(machine, name: str):
    found = machine.contexts.get(name)
    assert found is not None, f"no context named {name}; have {list(machine.contexts)}"
    return found


def patterns_of(context, lookup) -> list[str]:
    return [regex_of(rule.match.rule, lookup) for rule in context.rules]


# -- what a production becomes ---------------------------------------------


def test_a_production_that_brackets_something_is_a_span():
    _, parse = machine_of(LINES)
    classify = Classifier(parse)
    assert classify.of(parse.productions["Group"]) == SPAN


def test_a_production_that_runs_to_a_line_break_is_a_span():
    _, parse = machine_of(LINES)
    classify = Classifier(parse)
    assert classify.of(parse.productions["Definition"]) == SPAN


def test_a_classed_production_with_a_regular_form_is_a_token():
    _, parse = machine_of(LINES)
    classify = Classifier(parse)
    assert classify.of(parse.productions["Marker"]) == TOKEN


def test_an_unclassed_production_is_transparent():
    _, parse = machine_of(LINES)
    classify = Classifier(parse)
    assert classify.of(parse.productions["Items"]) == INLINE


# -- what a context holds ---------------------------------------------------


def test_a_line_role_is_entered_by_its_marker_and_left_at_the_line_end():
    machine, _ = machine_of(LINES)
    start = context_of(machine, machine.start)
    opening = [rule for rule in start.rules if rule.push]
    assert [rule.classes for rule in opening] == [["Keyword"], ["Comment"]]
    assert context_of(machine, opening[0].push).line_end == POP


def test_a_marker_is_a_keyword_only_where_a_line_may_open_with_one():
    """The whole point: `d` has no rule inside the line it opened."""
    machine, parse = machine_of(LINES)
    start = context_of(machine, machine.start)
    inside = context_of(machine, next(r.push for r in start.rules if r.push))
    assert "d" in patterns_of(start, parse.productions.get)
    assert "d" not in patterns_of(inside, parse.productions.get)


def test_a_group_holds_what_its_own_lines_hold_and_no_more():
    machine, parse = machine_of(LINES)
    group = context_of(machine, "Group")
    assert "d" not in patterns_of(group, parse.productions.get)
    # It closes on its bracket rather than at the end of a line, so it nests.
    assert group.line_end == STAY
    assert [rule.pop for rule in group.rules if rule.pop] == [1]


def test_a_span_that_colours_its_contents_keeps_the_class_on_the_context():
    machine, _ = machine_of(LINES)
    start = context_of(machine, machine.start)
    comment = context_of(machine, [r.push for r in start.rules if r.push][1])
    assert comment.classes == ["Comment"]


def test_a_marker_spelled_as_a_letter_matches_between_word_boundaries():
    machine, _ = machine_of(LINES)
    start = context_of(machine, machine.start)
    marker, hash_rule = [rule for rule in start.rules if rule.push]
    assert marker.match.word_boundary
    assert not hash_rule.match.word_boundary


def test_no_rule_of_a_context_can_match_nothing():
    """A zero-width rule makes no progress, so a context never holds one."""
    machine, parse = machine_of(MGFF.read_text(encoding="utf-8"), str(MGFF))
    for context in machine.contexts.values():
        for rule in context.rules:
            if not rule.match.look_ahead:
                pattern = regex_of(rule.match.rule, parse.productions.get)
                assert pattern != "" and pattern is not None


# -- chained line contexts --------------------------------------------------


def test_a_role_reaching_past_its_line_carries_on_into_a_context_of_its_own():
    """A definition's alternative lines belong to the definition, not the scope."""
    machine, parse = machine_of(MGFF.read_text(encoding="utf-8"), str(MGFF))
    definition = context_of(machine, "Definition")
    assert definition.line_end not in (STAY, POP)

    carried = context_of(machine, definition.line_end)
    openings = [rule for rule in carried.rules if rule.push]
    assert {rule.classes[0] for rule in openings} == {"ControlFlow", "Comment", "Operator"}
    # The scope below knows none of them: `|` is an alternative only here.
    start = context_of(machine, machine.start)
    assert "\\|" not in patterns_of(start, parse.productions.get)


def test_a_chain_is_left_by_a_line_it_does_not_recognise():
    machine, _ = machine_of(MGFF.read_text(encoding="utf-8"), str(MGFF))
    definition = context_of(machine, "Definition")
    carried = context_of(machine, definition.line_end)
    leaving = [rule for rule in carried.rules if rule.match.look_ahead]
    # One rule, popping the chain and the definition it belongs to, and matching
    # nothing at all — the line is read again by whatever is underneath.
    assert [rule.pop for rule in leaving] == [2]


def test_a_bracketed_span_is_never_left_by_a_line_it_does_not_recognise():
    """It ends on its closing character, wherever that is."""
    machine, _ = machine_of(MGFF.read_text(encoding="utf-8"), str(MGFF))
    for name in ("SubGroup", "ScopeGroup", "CommentGroup"):
        context = context_of(machine, name)
        assert not any(rule.match.look_ahead for rule in context.rules)


# -- states -----------------------------------------------------------------


def test_two_places_leaving_the_same_thing_behind_are_one_context():
    """A scope group's lines are a file's lines, so they share their context."""
    machine, _ = machine_of(MGFF.read_text(encoding="utf-8"), str(MGFF))
    scope = context_of(machine, "ScopeGroup")
    start = context_of(machine, machine.start)
    pushed = {rule.push for rule in scope.rules if rule.push}
    assert pushed == {rule.push for rule in start.rules if rule.push}


@pytest.mark.parametrize("path", ["kate.mgff", "textmate.mgff"])
def test_the_fixtures_build_a_machine(path):
    text = (Path(__file__).parent / "fixtures" / path).read_text(encoding="utf-8")
    machine, _ = machine_of(text, path)
    assert machine.contexts
