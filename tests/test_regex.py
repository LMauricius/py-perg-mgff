"""The regular-expression backend."""

import re
from pathlib import Path

import pytest

from pyperg.diagnostics.errors import GeneratorError
from pyperg.generators.regex import RegexGenerator
from pyperg.mgff.lexing.lexer import lex_text
from pyperg.mgff.semantics.model import parse, rule_tree_factory, resolve

def fixture_text(name: str) -> str:
    return (Path(__file__).parent / "fixtures" / name).read_text(encoding="utf-8")


def rendered_pattern_of(text: str, name: str = "<test>") -> str:
    """Resolve through the backend's own vocabulary, as `generate` does."""
    backend = RegexGenerator()
    fileScope = parse(lex_text(text, name), rule_tree_factory)
    return backend.render(resolve(fileScope, name, backend.macros()))


def matches_whole_string(pattern: str, text: str) -> bool:
    """Whether the pattern matches the whole of a string, Python's engine reading it."""
    return re.fullmatch(pattern, text) is not None


# -- the shape of a grammar the backend reads -------------------------------


def test_a_grammar_is_read_from_the_match_macro():
    assert rendered_pattern_of("d Match = a-z\nd Unused = 0-9") == "[a-z]"


def test_a_grammar_without_a_match_macro_is_reported():
    with pytest.raises(GeneratorError, match="no macro named 'Match'"):
        rendered_pattern_of("d Other = a-z")


def test_a_target_is_reported_rather_than_flattened():
    # One expression is one pass over the text, so there are no phases to have.
    with pytest.raises(GeneratorError, match="target"):
        rendered_pattern_of("t Lex (\n d Match = a-z\n)")


def test_a_reference_is_inlined():
    assert rendered_pattern_of("d Digit = 0-9\nd Match = ( Digit )+") == "[0-9]+"


def test_the_example_grammar_generates_a_usable_expression():
    pattern = rendered_pattern_of(fixture_text("regex.mgff"), "regex.mgff")
    assert matches_whole_string(pattern, "  size = 42 ")
    assert matches_whole_string(pattern, "name=value")
    assert not matches_whole_string(pattern, "size = ")


# -- capture groups ---------------------------------------------------------


def test_a_stored_production_becomes_a_named_group():
    pattern = rendered_pattern_of("d Word = ( a-z )+\n > store(word)\nd Match = Word")
    assert pattern == "(?P<word>[a-z]+)"
    match = re.fullmatch(pattern, "abc")
    assert match is not None and match["word"] == "abc"


def test_a_production_storing_nothing_captures_nothing():
    assert rendered_pattern_of("d Word = ( a-z )+\nd Match = Word 0-9") == "[a-z]+[0-9]"


def test_the_start_production_is_not_wrapped_in_its_own_field():
    """Nothing calls `Match`, so there is no caller for it to store itself in."""
    assert rendered_pattern_of("d Match = ( a-z )+\n > store(all)") == "[a-z]+"


def test_a_stored_production_reached_twice_is_reported():
    # The production is written into the expression once per use, and no engine
    # allows a name to appear twice.
    with pytest.raises(GeneratorError, match="more than once"):
        rendered_pattern_of("d Word = a-z\n > store(w)\nd Match = Word Word")


def test_a_name_no_engine_accepts_is_reported():
    with pytest.raises(GeneratorError, match="no name for a field"):
        rendered_pattern_of("d Word = a-z\n > store(2go)\nd Match = Word")


def test_push_has_no_meaning_in_one_expression():
    with pytest.raises(GeneratorError, match="no meaning in one expression"):
        rendered_pattern_of("d Word = a-z\n > push(words)\nd Match = Word")


# -- recursion --------------------------------------------------------------


def test_right_linear_recursion_becomes_a_repetition():
    pattern = rendered_pattern_of("d Match = 0-9 Match\n/ 0-9")
    assert matches_whole_string(pattern, "42")
    assert not matches_whole_string(pattern, "4a")


def test_left_linear_recursion_becomes_a_repetition():
    pattern = rendered_pattern_of("d Match = Match 0-9\n/ 0-9")
    assert matches_whole_string(pattern, "42")
    assert not matches_whole_string(pattern, "")


def test_mutual_recursion_is_solved_as_one_system():
    # A = a B / a, B = b A / b: the strings that alternate, starting with `a`.
    pattern = rendered_pattern_of("d A = a B\n/ a\nd B = b A\n/ b\nd Match = A")
    assert matches_whole_string(pattern, "a") and matches_whole_string(pattern, "abab")
    assert not matches_whole_string(pattern, "ba") and not matches_whole_string(pattern, "aa")


def test_recursion_with_text_on_both_sides_is_reported():
    with pytest.raises(GeneratorError, match="both sides"):
        rendered_pattern_of("d Match = \\( Match \\)\n/ a")


def test_recursion_nested_inside_a_repetition_is_reported():
    with pytest.raises(GeneratorError, match="nested inside"):
        rendered_pattern_of("d Match = ( Match )* a")


def test_a_group_recursing_on_both_sides_is_reported():
    with pytest.raises(GeneratorError, match="start of one alternative"):
        rendered_pattern_of("d Match = Match a\n/ b Match\n/ c")


def test_every_culprit_production_is_named():
    text = "d Match = A\nd A = \\( A \\)\n/ B\nd B = [ B ]\n/ b"
    with pytest.raises(GeneratorError) as raised:
        rendered_pattern_of(text)
    message = str(raised.value)
    assert "  A:" in message and "  B:" in message


def test_recursion_that_never_ends_is_reported():
    with pytest.raises(GeneratorError, match="matches nothing"):
        rendered_pattern_of("d Match = Match a")


# -- the file it writes -----------------------------------------------------


def test_the_expression_is_written_as_one_file(tmp_path):
    backend = RegexGenerator()
    fileScope = parse(
        lex_text(fixture_text("regex.mgff"), "regex.mgff"), rule_tree_factory
    )
    model = resolve(
        fileScope,
        "regex.mgff",
        backend.macros(),
    )
    written_paths = backend.generate(model, tmp_path)
    assert [path.name for path in written_paths] == ["regex.regex"]
    assert written_paths[0].read_text(encoding="utf-8").strip() == backend.render(model)


def test_an_empty_group_repeats_as_an_empty_group():
    """A quantifier needs something to apply to, and `*` on its own is no pattern."""
    pattern = rendered_pattern_of("d Match = ( )+\n")
    assert pattern == "(?:)+"
    assert re.fullmatch(pattern, "") is not None
