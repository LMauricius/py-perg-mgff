"""The lexical layer (specification Part 1)."""

from pathlib import Path

import pytest

from pyperg.diagnostics.errors import ItemizationError
from pyperg.mgff.itemizing.cst import Group, Text, render_item
from pyperg.mgff.itemizing.itemizer import itemize_text

FIXTURE = Path(__file__).parent / "fixtures" / "calc.mgff"


def items_of_single_line(text: str):
    """The items of a single-line source."""
    file = itemize_text(text)
    assert len(file.lines) == 1
    return file.lines[0].items


def test_five_items_of_the_specification_example():
    """`d Number = Int ( . ( Digit )+ )?` is five items, the last one glued."""
    line_items = items_of_single_line("    d Number = Int ( . ( Digit )+ )?")
    assert [item.text for item in line_items] == ["d", "Number", "=", "Int", "?"]
    assert line_items[-1].groups  # the text "?" is glued to a group


def test_space_outside_parentheses_separates():
    """`< =` is two items; the separating space is outside any group."""
    assert [item.text for item in items_of_single_line("< =")] == ["<", "="]


def test_group_spans_lines():
    """A line ends only at a newline outside every group."""
    file = itemize_text("t Lex (\n    d Digit = 0-9\n)")
    assert len(file.lines) == 1
    group = file.lines[0].items[-1].groups[0]
    assert [len(line.items) for line in group.lines] == [0, 4, 0]


def test_item_alternates_text_and_groups():
    item = items_of_single_line("sep(R)by(S)")[0]
    assert item.text == "sepby"
    assert [type(part) for part in item.parts] == [Text, Group, Text, Group]


def test_two_adjacent_groups_are_an_error():
    with pytest.raises(ItemizationError, match="separated by text"):
        itemize_text("(a)(b)")


@pytest.mark.parametrize("text", ["(a", "a)", "t Lex ( d x = y"])
def test_unbalanced_parentheses(text):
    with pytest.raises(ItemizationError):
        itemize_text(text)


def test_escaped_parenthesis_is_text():
    item = items_of_single_line(r"\(")[0]
    assert item.text == "("
    assert not item.groups


def test_blank_lines_carry_no_items_of_single_line():
    file = itemize_text("d a = b\n\n   \t \nd c = d")
    assert [line.is_blank for line in file.lines] == [False, True, True, False]


def test_spans_point_at_the_source():
    item = items_of_single_line("  Digit")[0]
    assert (item.span.start.line, item.span.start.column) == (1, 3)
    assert item.span.end.column == 8


def test_error_carries_a_span():
    with pytest.raises(ItemizationError) as excinfo:
        itemize_text("d x = y\nd z = (a)(b)")
    assert excinfo.value.span is not None
    assert excinfo.value.span.start.line == 2


def test_appendix_example_lexes():
    file = itemize_text(FIXTURE.read_text(encoding="utf-8"), FIXTURE.name)
    first_item_texts = [line.items[0].text for line in file.lines if not line.is_blank]
    assert first_item_texts.count("t") == 2  # the Lex and Parse targets
    assert "d" in first_item_texts  # the top-level sep(R)by(S) macro


def test_render_round_trips_an_item():
    assert (
        render_item(items_of_single_line("sep(Ident = Expr)by(,)")[0])
        == "sep(Ident = Expr)by(,)"
    )


def test_nesting_has_a_limit():
    """A file no one wrote by hand is reported, not left to exhaust the stack."""
    with pytest.raises(ItemizationError, match="nested more than"):
        itemize_text("d X = " + "(" * 400 + "a" + ")" * 400)


def test_a_stray_carriage_return_says_so():
    """A `\\r` outside a `\\r\\n` pair ends nothing, and the message says which."""
    with pytest.raises(ItemizationError, match="stray carriage return"):
        itemize_text("d A = a\rd B = b")
