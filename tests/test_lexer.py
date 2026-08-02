"""The lexical layer (specification Part 1)."""

from pathlib import Path

import pytest

from pyperg.diagnostics.errors import LexError
from pyperg.mgff.lexing.cst import Group, Text, render_item
from pyperg.mgff.lexing.lexer import lex_text

FIXTURE = Path(__file__).parent / "fixtures" / "calc.mgff"


def items(text: str):
    """The items of a single-line source."""
    file = lex_text(text)
    assert len(file.lines) == 1
    return file.lines[0].items


def test_five_items_of_the_specification_example():
    """`d Number = Int ( . ( Digit )+ )?` is five items, the last one glued."""
    line = items("    d Number = Int ( . ( Digit )+ )?")
    assert [i.text for i in line] == ["d", "Number", "=", "Int", "?"]
    assert line[-1].groups  # the text "?" is glued to a group


def test_space_outside_parentheses_separates():
    """`< =` is two items; the separating space is outside any group."""
    assert [i.text for i in items("< =")] == ["<", "="]


def test_group_spans_lines():
    """A line ends only at a newline outside every group."""
    file = lex_text("t Lex (\n    d Digit = 0-9\n)")
    assert len(file.lines) == 1
    group = file.lines[0].items[-1].groups[0]
    assert [len(line.items) for line in group.lines] == [0, 4, 0]


def test_item_alternates_text_and_groups():
    item = items("sep(R)by(S)")[0]
    assert item.text == "sepby"
    assert [type(p) for p in item.parts] == [Text, Group, Text, Group]


def test_two_adjacent_groups_are_an_error():
    with pytest.raises(LexError, match="separated by text"):
        lex_text("(a)(b)")


@pytest.mark.parametrize("text", ["(a", "a)", "t Lex ( d x = y"])
def test_unbalanced_parentheses(text):
    with pytest.raises(LexError):
        lex_text(text)


def test_escaped_parenthesis_is_text():
    item = items(r"\(")[0]
    assert item.text == "("
    assert not item.groups


def test_blank_lines_carry_no_items():
    file = lex_text("d a = b\n\n   \t \nd c = d")
    assert [line.is_blank for line in file.lines] == [False, True, True, False]


def test_spans_point_at_the_source():
    item = items("  Digit")[0]
    assert (item.span.start.line, item.span.start.column) == (1, 3)
    assert item.span.end.column == 8


def test_error_carries_a_span():
    with pytest.raises(LexError) as excinfo:
        lex_text("d x = y\nd z = (a)(b)")
    assert excinfo.value.span is not None
    assert excinfo.value.span.start.line == 2


def test_appendix_example_lexes():
    file = lex_text(FIXTURE.read_text(encoding="utf-8"), FIXTURE.name)
    tops = [line.items[0].text for line in file.lines if not line.is_blank]
    assert tops.count("t") == 2  # the Lex and Parse targets
    assert "d" in tops  # the top-level sep(R)by(S) macro


def test_render_round_trips_an_item():
    assert render_item(items("sep(Ident = Expr)by(,)")[0]) == "sep(Ident = Expr)by(,)"
