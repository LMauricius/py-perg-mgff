"""The regular-expression backend."""

import re
from pathlib import Path

import pytest

from pyperg.diagnostics.errors import GeneratorError
from pyperg.generators.regex import RegexGenerator
from pyperg.mgff.lexing.lexer import lex_text
from pyperg.mgff.semantics.model import resolve


def read_fixture(name: str) -> str:
    return (Path(__file__).parent / "fixtures" / name).read_text(encoding="utf-8")


def render(text: str, name: str = "<test>") -> str:
    """Resolve through the backend's own vocabulary, as `generate` does."""
    backend = RegexGenerator()
    return backend.render(resolve(lex_text(text, name), name, backend.macros()))


def matches(pattern: str, text: str) -> bool:
    """Whether the pattern matches the whole of a string, Python's engine reading it."""
    return re.fullmatch(pattern, text) is not None


# -- the shape of a grammar the backend reads -------------------------------


def test_a_grammar_is_read_from_the_match_macro():
    assert render("d Match = a-z\nd Unused = 0-9") == "[a-z]"


def test_a_grammar_without_a_match_macro_is_reported():
    with pytest.raises(GeneratorError, match="no macro named 'Match'"):
        render("d Other = a-z")


def test_a_target_is_reported_rather_than_flattened():
    # One expression is one pass over the text, so there are no phases to have.
    with pytest.raises(GeneratorError, match="target"):
        render("t Lex (\n d Match = a-z\n)")


def test_a_reference_is_inlined():
    assert render("d Digit = 0-9\nd Match = ( Digit )+") == "[0-9]+"


def test_the_example_grammar_generates_a_usable_expression():
    pattern = render(read_fixture("regex.mgff"), "regex.mgff")
    assert matches(pattern, "  size = 42 ")
    assert matches(pattern, "name=value")
    assert not matches(pattern, "size = ")


# -- capture groups ---------------------------------------------------------


def test_a_named_group_keeps_its_name():
    pattern = render("d Match = word:( ( a-z )+ )")
    assert pattern == "(?P<word>[a-z]+)"
    found = re.fullmatch(pattern, "abc")
    assert found is not None and found["word"] == "abc"


def test_an_unnamed_group_captures_by_position():
    pattern = render("d Match = :( ( a-z )+ ) 0-9")
    assert pattern == "([a-z]+)[0-9]"
    found = re.fullmatch(pattern, "abc1")
    assert found is not None and found[1] == "abc"


def test_a_name_used_twice_is_reported():
    # The production is written into the expression once per use, and no engine
    # allows a name to appear twice.
    with pytest.raises(GeneratorError, match="more than once"):
        render("d Word = w:( a-z )\nd Match = Word Word")


def test_a_name_no_engine_accepts_is_reported():
    with pytest.raises(GeneratorError, match="no name for a capture group"):
        render("d Match = 2go:( a-z )")


# -- recursion --------------------------------------------------------------


def test_right_linear_recursion_becomes_a_repetition():
    pattern = render("d Match = 0-9 Match\n/ 0-9")
    assert matches(pattern, "42")
    assert not matches(pattern, "4a")


def test_left_linear_recursion_becomes_a_repetition():
    pattern = render("d Match = Match 0-9\n/ 0-9")
    assert matches(pattern, "42")
    assert not matches(pattern, "")


def test_mutual_recursion_is_solved_as_one_system():
    # A = a B / a, B = b A / b: the strings that alternate, starting with `a`.
    pattern = render("d A = a B\n/ a\nd B = b A\n/ b\nd Match = A")
    assert matches(pattern, "a") and matches(pattern, "abab")
    assert not matches(pattern, "ba") and not matches(pattern, "aa")


def test_recursion_with_text_on_both_sides_is_reported():
    with pytest.raises(GeneratorError, match="both sides"):
        render("d Match = \\( Match \\)\n/ a")


def test_recursion_nested_inside_a_repetition_is_reported():
    with pytest.raises(GeneratorError, match="nested inside"):
        render("d Match = ( Match )* a")


def test_a_group_recursing_on_both_sides_is_reported():
    with pytest.raises(GeneratorError, match="start of one alternative"):
        render("d Match = Match a\n/ b Match\n/ c")


def test_every_culprit_production_is_named():
    text = "d Match = A\nd A = \\( A \\)\n/ B\nd B = [ B ]\n/ b"
    with pytest.raises(GeneratorError) as raised:
        render(text)
    message = str(raised.value)
    assert "  A:" in message and "  B:" in message


def test_recursion_that_never_ends_is_reported():
    with pytest.raises(GeneratorError, match="matches nothing"):
        render("d Match = Match a")


# -- the file it writes -----------------------------------------------------


def test_the_expression_is_written_as_one_file(tmp_path):
    backend = RegexGenerator()
    model = resolve(
        lex_text(read_fixture("regex.mgff"), "regex.mgff"),
        "regex.mgff",
        backend.macros(),
    )
    written = backend.generate(model, tmp_path)
    assert [path.name for path in written] == ["regex.regex"]
    assert written[0].read_text(encoding="utf-8").strip() == backend.render(model)
