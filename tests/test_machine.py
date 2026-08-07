"""The highlighting machine: what may appear where, derived from `Parse`."""

from pathlib import Path

import pytest

from pyperg.diagnostics.errors import GeneratorError
from pyperg.generators.kate import KateGenerator
from pyperg.generators.utils.highlight import token_names_in_order
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

MGFF = Path(__file__).parent.parent / "examples" / "mgff.mgff"

# A grammar of line roles: a marker opens a line, a group holds items and
# nothing else, and a comment reaches past its line through a group.
LINES = """
t Lex (
    d Marker = d
        > style(Keyword)
    d Hash = #
        > style(Comment)
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
        > style(Comment)
    d Line = (Definition)/(Comment)
    d File = ( (Line)/(NewLine) )*
)
"""


def build_machine_from_text(text: str, name: str = "<test>"):
    model = resolve(lex_text(text, name), name, KateGenerator().macros())
    parse_target = model.target("Parse")
    lex_target = model.target("Lex")
    return (
        MachineBuilder(
            parse_target, token_names_in_order(lex_target) if lex_target else []
        ).build(),
        parse_target,
    )


def context_of(machine, name: str):
    context = machine.contexts.get(name)
    assert (
        context is not None
    ), f"no context named {name}; have {list(machine.contexts)}"
    return context


def patterns_for_context(context, find_production) -> list[str]:
    return [regex_of(rule.match.rule, find_production) for rule in context.rules]


# -- what a production becomes ---------------------------------------------


def test_a_production_that_brackets_something_is_a_span():
    _, parse_target = build_machine_from_text(LINES)
    classifier = Classifier(parse_target)
    assert classifier.role_of(parse_target.productions["Group"]) == SPAN


def test_a_production_that_runs_to_a_line_break_is_a_span():
    _, parse_target = build_machine_from_text(LINES)
    classifier = Classifier(parse_target)
    assert classifier.role_of(parse_target.productions["Definition"]) == SPAN


def test_a_styled_production_with_a_regular_form_is_a_token():
    _, parse_target = build_machine_from_text(LINES)
    classifier = Classifier(parse_target)
    assert classifier.role_of(parse_target.productions["Marker"]) == TOKEN


def test_an_unclassed_production_is_transparent():
    _, parse_target = build_machine_from_text(LINES)
    classifier = Classifier(parse_target)
    assert classifier.role_of(parse_target.productions["Items"]) == INLINE


# -- what a context holds ---------------------------------------------------


def test_a_line_role_is_entered_by_its_marker_and_left_at_the_line_end():
    machine, _ = build_machine_from_text(LINES)
    start_context = context_of(machine, machine.start)
    opening_rules = [rule for rule in start_context.rules if rule.push]
    assert [rule.styles for rule in opening_rules] == [["Keyword"], ["Comment"]]
    assert context_of(machine, opening_rules[0].push).line_end == POP


def test_a_marker_is_a_keyword_only_where_a_line_may_open_with_one():
    """The whole point: `d` has no rule inside the line it opened."""
    machine, parse_target = build_machine_from_text(LINES)
    start_context = context_of(machine, machine.start)
    inside_context = context_of(
        machine, next(rule.push for rule in start_context.rules if rule.push)
    )
    assert "d" in patterns_for_context(start_context, parse_target.productions.get)
    assert "d" not in patterns_for_context(inside_context, parse_target.productions.get)


def test_a_group_holds_what_its_own_lines_hold_and_no_more():
    machine, parse_target = build_machine_from_text(LINES)
    group = context_of(machine, "Group")
    assert "d" not in patterns_for_context(group, parse_target.productions.get)
    # It closes on its bracket rather than at the end of a line, so it nests.
    assert group.line_end == STAY
    assert [rule.pop for rule in group.rules if rule.pop] == [1]


def test_a_span_that_colours_its_contents_keeps_the_style_on_the_context():
    machine, _ = build_machine_from_text(LINES)
    start_context = context_of(machine, machine.start)
    comment = context_of(
        machine, [rule.push for rule in start_context.rules if rule.push][1]
    )
    assert comment.styles == ["Comment"]


def test_a_marker_spelled_as_a_letter_matches_between_word_boundaries():
    machine, _ = build_machine_from_text(LINES)
    start_context = context_of(machine, machine.start)
    marker, hash_rule = [rule for rule in start_context.rules if rule.push]
    assert marker.match.word_boundary
    assert not hash_rule.match.word_boundary


def test_no_rule_of_a_context_can_match_nothing():
    """A zero-width rule makes no progress, so a context never holds one."""
    machine, parse_target = build_machine_from_text(
        MGFF.read_text(encoding="utf-8"), str(MGFF)
    )
    for context in machine.contexts.values():
        for rule in context.rules:
            if not rule.match.look_ahead:
                pattern = regex_of(rule.match.rule, parse_target.productions.get)
                assert pattern != "" and pattern is not None


# -- chained line contexts --------------------------------------------------


def test_a_role_reaching_past_its_line_carries_on_into_a_context_of_its_own():
    """A definition's alternative lines belong to the definition, not the scope."""
    machine, parse_target = build_machine_from_text(
        MGFF.read_text(encoding="utf-8"), str(MGFF)
    )
    definition = context_of(machine, "Definition")
    assert definition.line_end not in (STAY, POP)

    carried_context = context_of(machine, definition.line_end)
    openings = [rule for rule in carried_context.rules if rule.push]
    assert {rule.styles[0] for rule in openings} == {
        "ControlFlow",
        "Comment",
        "Operator",
    }
    # The scope below knows none of them: `|` is an alternative only here.
    start_context = context_of(machine, machine.start)
    assert "\\|" not in patterns_for_context(
        start_context, parse_target.productions.get
    )


def test_a_chain_is_left_by_a_line_it_does_not_recognise():
    machine, _ = build_machine_from_text(MGFF.read_text(encoding="utf-8"), str(MGFF))
    definition = context_of(machine, "Definition")
    carried_context = context_of(machine, definition.line_end)
    leaving_rules = [rule for rule in carried_context.rules if rule.match.look_ahead]
    # One rule, popping the chain and the definition it belongs to, and matching
    # nothing at all — the line is read again by whatever is underneath.
    assert [rule.pop for rule in leaving_rules] == [2]


def test_a_bracketed_span_is_never_left_by_a_line_it_does_not_recognise():
    """It ends on its closing character, wherever that is."""
    machine, _ = build_machine_from_text(MGFF.read_text(encoding="utf-8"), str(MGFF))
    for name in ("SubGroup", "ScopeGroup", "CommentGroup"):
        context = context_of(machine, name)
        assert not any(rule.match.look_ahead for rule in context.rules)


# -- states -----------------------------------------------------------------


def test_two_places_leaving_the_same_thing_behind_are_one_context():
    """A scope group's lines are a file's lines, so they share their context."""
    machine, _ = build_machine_from_text(MGFF.read_text(encoding="utf-8"), str(MGFF))
    scope_context = context_of(machine, "ScopeGroup")
    start_context = context_of(machine, machine.start)
    pushed_context_names = {rule.push for rule in scope_context.rules if rule.push}
    assert pushed_context_names == {
        rule.push for rule in start_context.rules if rule.push
    }


@pytest.mark.parametrize("path", ["kate.mgff", "textmate.mgff"])
def test_the_fixtures_build_a_machine(path):
    text = (Path(__file__).parent / "fixtures" / path).read_text(encoding="utf-8")
    machine, _ = build_machine_from_text(text, path)
    assert machine.contexts


# -- grammars the machine cannot spell --------------------------------------


def test_a_recursive_token_does_not_send_the_walk_round_forever():
    """A production reaching itself is not one expression's worth of matching."""
    text = (
        "t Lex (\n"
        "    d File = ( A )*\n"
        "    d A = a A / a\n"
        "      > style(Keyword) class(A) push(t)\n"
        ")\n"
        "t Parse (\n"
        "    > post(Lex) over(t)\n"
        "    d File = ( A )*\n"
        ")\n"
    )
    machine, _ = build_machine_from_text(text)
    assert machine.contexts


def test_a_rule_leaving_more_behind_after_every_line_is_reported():
    """There is no machine for a role that never reaches a line it may end on."""
    text = (
        "t Lex (\n"
        "    d File = ( A )*\n"
        "    d A = a\n"
        "      > style(Keyword) class(a) push(t)\n"
        ")\n"
        "t Parse (\n"
        "    > post(Lex)\n"
        "    d File = B\n"
        "    d B = \\n B a\n"
        ")\n"
    )
    with pytest.raises(GeneratorError, match="leaves more behind"):
        build_machine_from_text(text)


def test_a_production_is_classified_the_same_whoever_asks_first():
    """Two mutually recursive line roles settle on one answer, not on an order."""
    text = (
        "t Parse (\n"
        "    d File = ( X )*\n"
        "    d X = a Y \\n\n"
        "    d Y = b X / b\n"
        ")\n"
    )
    model = resolve(lex_text(text, "<test>"), "<test>", KateGenerator().macros())
    parse_target = model.target("Parse")
    assert parse_target is not None

    roles_per_starting_production = []
    for first_asked in ("X", "Y"):
        classifier = Classifier(parse_target)
        classifier.role_of(parse_target.productions[first_asked])
        roles_per_starting_production.append(
            {
                name: classifier.role_of(production)
                for name, production in parse_target.productions.items()
            }
        )
    assert roles_per_starting_production[0] == roles_per_starting_production[1]
