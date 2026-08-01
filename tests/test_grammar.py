"""Grammar semantics (specification Part 2): scopes, targets and macros."""

from pathlib import Path

import pytest

from pyperg.diagnostics.errors import SemanticError, SyntaxError_
from pyperg.grammar.parser import parse
from pyperg.mgff.lexer import lex_text

CALC = Path(__file__).parent / "fixtures" / "calc.mgff"
PREFIX = Path(__file__).parent / "fixtures" / "prefix.mgff"


def read(text: str):
    """Parse a source string into its file scope."""
    return parse(lex_text(text))


def read_fixture(path: Path):
    return parse(lex_text(path.read_text(encoding="utf-8"), str(path)))


# -- the specification's own example ---------------------------------------


def test_targets_of_the_calculator_grammar():
    root = read_fixture(CALC)
    assert sorted(root.targets) == ["Lex", "Parse"]
    assert "Digit" in root.targets["Lex"].macros
    assert "RParen" in root.targets["Lex"].macros


def test_length_based_and_order_based_alternatives():
    root = read_fixture(CALC)
    op = root.targets["Lex"].macros["Op"]
    assert op.choice_symbol == "|"
    assert len(op.options) == 7

    expr = root.targets["Parse"].macros["Expr"]
    assert expr.choice_symbol == "/"
    assert len(expr.options) == 3


def test_a_single_alternative_has_no_choice_symbol():
    macro = read("d Digit = 0-9").macros["Digit"]
    assert macro.choice_symbol is None
    assert len(macro.options) == 1


def test_the_second_slash_of_a_line_is_ordinary():
    """On `/ Factor / Term` only the leading `/` is a marker."""
    term = read_fixture(CALC).targets["Parse"].macros["Term"]
    assert [len(option) for option in term.options] == [3, 3, 1]


def test_attributes_accumulate_over_lines():
    root = read_fixture(CALC)
    number = root.targets["Lex"].macros["Number"]
    # Attributes stay unread items; `skip(false)` is text `skip` plus one group.
    assert [item.text for item in number.attributes] == ["token", "skip"]
    assert number.attributes[1].groups
    assert len(number.attribute_lists) == 1

    space = root.targets["Lex"].macros["Space"]
    assert [item.text for item in space.attributes] == ["token", "skip"]


def test_a_comment_does_not_end_a_macro():
    macro = read("d x = a\n# comment\n/ b").macros["x"]
    assert len(macro.options) == 2


def test_a_macro_may_bear_a_marker_name():
    """The head is read only after `d`, so any name will do."""
    root = read("d / = a")
    assert "/" in root.macros


def test_an_empty_body_is_an_empty_option():
    macro = read("d x =").macros["x"]
    assert macro.options == [[]]
    assert not macro.matches_nothing


def test_a_definition_separated_by_a_marker_has_no_options():
    """`d Head > Attributes` is how a named list of attributes is written."""
    macro = read("d Common > token skip(false)").macros["Common"]
    assert macro.options == []
    assert macro.matches_nothing
    assert [item.text for item in macro.attributes] == ["token", "skip"]


def test_further_attribute_lines_add_to_an_option_less_macro():
    macro = read("d Common > token\n> string").macros["Common"]
    assert macro.matches_nothing
    assert [item.text for item in macro.attributes] == ["token", "string"]


def test_an_option_less_macro_takes_no_alternatives():
    with pytest.raises(SyntaxError_) as excinfo:
        read("d Common > token\n/ a")
    assert "may not follow" in excinfo.value.message


# -- parameters and signatures ---------------------------------------------


def test_a_mixfix_head_gives_a_signature_and_parameters():
    macro = read_fixture(PREFIX).macros["sep()by()"]
    assert macro.name == "sepby"
    assert macro.parameters == ["R", "S"]


def test_a_macro_remembers_the_scope_it_was_defined_in():
    root = read_fixture(PREFIX)
    assert root.macros["sep()by()"].scope is root
    assert root.targets["Parse"].macros["Expr"].scope is root.targets["Parse"]


# -- prefixes ---------------------------------------------------------------


def test_nested_prefixes_concatenate():
    root = read_fixture(PREFIX)
    util = root.subscopes["Util_"]
    inner = util.subscopes["Inner_"]

    assert "list" in inner.macros
    assert "Inner_list" in util.macros
    assert "Util_Inner_list" in root.macros
    # One macro, reachable under three names; it belongs to the innermost scope.
    assert root.macros["Util_Inner_list"] is inner.macros["list"]
    assert inner.macros["list"].scope is inner


def test_a_prefixed_macro_is_called_by_its_local_name_from_within():
    root = read_fixture(PREFIX)
    inner = root.subscopes["Util_"].subscopes["Inner_"]
    assert inner.lookup("list") is inner.macros["list"]
    assert inner.lookup("sep()by()") is root.macros["sep()by()"]
    # The full name also resolves from within, since lookup carries on outwards.
    assert inner.lookup("Util_Inner_list") is inner.macros["list"]
    assert root.lookup("list") is None  # but the local name does not escape


def test_a_target_keeps_its_macros_to_itself():
    root = read_fixture(CALC)
    assert "Digit" not in root.macros
    assert root.targets["Lex"].lookup("sep()by()") is root.macros["sep()by()"]


def test_a_scope_knows_its_qualified_name():
    root = read_fixture(PREFIX)
    assert root.subscopes["Util_"].subscopes["Inner_"].qualified_name == "Util_Inner_"


# -- errors -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("source", "message"),
    [
        ("x = a", "names no role"),
        ("/ a", "no macro to attach to"),
        ("> token", "no macro to attach to"),
        ("d x = a\n/ b\n| c", "same marker"),
        ("d x = a\n> token\n/ b", "may not follow"),
        ("d x a", "needs `=` or `>` right after the head"),
        ("d x", "needs `=` or `>` right after the head"),
        ("d", "needs a head"),
        ("t Lex", "written `t Name ( … )`"),
        ("p P_ x (\n)", "written `p Name ( … )`"),
        ("d f(a b) = a", "one plain name"),
    ],
)
def test_bad_lines_are_rejected(source, message):
    with pytest.raises((SyntaxError_, SemanticError)) as excinfo:
        read(source)
    assert message in excinfo.value.message
    assert excinfo.value.span is not None


def test_a_name_may_not_be_defined_twice():
    with pytest.raises(SemanticError):
        read("d x = a\nd x = b")


def test_a_prefix_may_not_collide_with_an_outer_name():
    with pytest.raises(SemanticError):
        read("d Util_x = a\np Util_ (\n    d x = b\n)")
