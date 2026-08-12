"""Grammar semantics (specification Part 2): scopes, targets and macros."""

from pathlib import Path

import pytest

from pyperg.diagnostics.errors import GrammarSyntaxError, SemanticError
from pyperg.mgff.semantics.parser import parse
from pyperg.mgff.itemizing.itemizer import itemize_text

CALC = Path(__file__).parent / "fixtures" / "calc.mgff"
PREFIX = Path(__file__).parent / "fixtures" / "prefix.mgff"


def parse_source(text: str):
    """Parse a source string into its file scope."""
    return parse(itemize_text(text))


def parse_fixture_file(path: Path):
    return parse(itemize_text(path.read_text(encoding="utf-8"), str(path)))


# -- the specification's own example ---------------------------------------


def test_targets_of_the_calculator_grammar():
    root = parse_fixture_file(CALC)
    assert sorted(root.targets) == ["Lex", "Parse"]
    assert "Digit" in root.targets["Lex"].sources
    assert "RParen" in root.targets["Lex"].sources


def test_length_based_and_order_based_alternatives():
    root = parse_fixture_file(CALC)
    operator_macro = root.targets["Lex"].sources["Op"]
    assert operator_macro.choice_symbol == "|"
    assert len(operator_macro.options) == 7

    expr = root.targets["Parse"].sources["Expr"]
    assert expr.choice_symbol == "/"
    assert len(expr.options) == 3


def test_a_single_alternative_has_no_choice_symbol():
    macro = parse_source("d Digit = 0-9").sources["Digit"]
    assert macro.choice_symbol is None
    assert len(macro.options) == 1


def test_the_second_slash_of_a_line_is_ordinary():
    """On `/ Factor / Term` only the leading `/` is a marker."""
    term = parse_fixture_file(CALC).targets["Parse"].sources["Term"]
    assert [len(option) for option in term.options] == [3, 3, 1]


def test_attributes_accumulate_over_lines():
    root = parse_fixture_file(CALC)
    number = root.targets["Lex"].sources["Number"]
    # Attributes stay unread items; `skip(false)` is text `skip` plus one group.
    assert [item.text for item in number.attributes] == ["token", "skip"]
    assert number.attributes[1].groups
    assert len(number.attribute_lists) == 1

    space = root.targets["Lex"].sources["Space"]
    assert [item.text for item in space.attributes] == ["token", "skip"]


def test_a_comment_does_not_end_a_macro():
    macro = parse_source("d x = a\n# comment\n/ b").sources["x"]
    assert len(macro.options) == 2


def test_a_macro_may_bear_a_marker_name():
    """The head is read only after `d`, so any name will do."""
    root = parse_source("d / = a")
    assert "/" in root.sources


def test_an_empty_body_is_an_empty_option():
    macro = parse_source("d x =").sources["x"]
    assert macro.options == [[]]
    assert not macro.matches_nothing


def test_a_definition_separated_by_a_marker_has_no_options():
    """`d Head > Attributes` is how a named list of attributes is written."""
    macro = parse_source("d Common > token skip(false)").sources["Common"]
    assert macro.options == []
    assert macro.matches_nothing
    assert [item.text for item in macro.attributes] == ["token", "skip"]


def test_further_attribute_lines_add_to_an_option_less_macro():
    macro = parse_source("d Common > token\n> string").sources["Common"]
    assert macro.matches_nothing
    assert [item.text for item in macro.attributes] == ["token", "string"]


def test_a_scope_carries_the_attribute_lines_at_its_top():
    """A `>` line with no macro above it describes the scope itself."""
    root = parse_source("> name(Toy) section(Sources)\n> license(MIT)\nd x = a")
    assert [item.text for item in root.attributes] == ["name", "section", "license"]


def test_a_target_carries_its_own_attributes():
    root = parse_source("t Parse (\n > post(Lex) over(tokens)\n d x = a\n)")
    target = root.targets["Parse"]
    assert [item.text for item in target.attributes] == ["post", "over"]
    assert not root.attributes


def test_an_option_less_macro_takes_no_alternatives():
    with pytest.raises(GrammarSyntaxError) as excinfo:
        parse_source("d Common > token\n/ a")
    assert "may not follow" in excinfo.value.message


# -- parameters and signatures ---------------------------------------------


def test_a_mixfix_head_gives_a_signature_and_parameters():
    macro = parse_fixture_file(PREFIX).sources["sep()by()"]
    assert macro.name == "sepby"
    assert macro.parameters == ["R", "S"]


def test_a_macro_remembers_the_scope_it_was_defined_in():
    root = parse_fixture_file(PREFIX)
    assert root.sources["sep()by()"].scope is root
    assert root.targets["Parse"].sources["Expr"].scope is root.targets["Parse"]


# -- prefixes ---------------------------------------------------------------


def test_nested_prefixes_concatenate():
    root = parse_fixture_file(PREFIX)
    util = root.subscopes["Util_"]
    inner = util.subscopes["Inner_"]

    assert "list" in inner.sources
    assert "Inner_list" in util.sources
    assert "Util_Inner_list" in root.sources
    # One macro, reachable under three names; it belongs to the innermost scope.
    assert root.sources["Util_Inner_list"] is inner.sources["list"]
    assert inner.sources["list"].scope is inner


def test_a_prefixed_macro_is_called_by_its_local_name_from_within():
    root = parse_fixture_file(PREFIX)
    inner = root.subscopes["Util_"].subscopes["Inner_"]
    assert inner.find_source("list") is inner.sources["list"]
    assert inner.find_source("sep()by()") is root.sources["sep()by()"]
    # The full name also resolves from within, since lookup carries on outwards.
    assert inner.find_source("Util_Inner_list") is inner.sources["list"]
    assert root.find_source("list") is None  # but the local name does not escape


def test_a_target_keeps_its_macros_to_itself():
    root = parse_fixture_file(CALC)
    assert "Digit" not in root.sources
    assert root.targets["Lex"].find_source("sep()by()") is root.sources["sep()by()"]


def test_a_scope_knows_its_qualified_name():
    root = parse_fixture_file(PREFIX)
    assert root.subscopes["Util_"].subscopes["Inner_"].qualified_name == "Util_Inner_"


# -- errors -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("source", "message"),
    [
        ("x = a", "names no role"),
        ("/ a", "no macro to attach to"),
        ("d x = a\nt Lex (\n)\n> token", "no macro to attach to"),
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
    with pytest.raises((GrammarSyntaxError, SemanticError)) as excinfo:
        parse_source(source)
    assert message in excinfo.value.message
    assert excinfo.value.span is not None


def test_a_name_may_not_be_defined_twice():
    with pytest.raises(SemanticError):
        parse_source("d x = a\nd x = b")


def test_a_prefix_may_not_collide_with_an_outer_name():
    with pytest.raises(SemanticError):
        parse_source("d Util_x = a\np Util_ (\n    d x = b\n)")


def test_a_target_inside_a_prefix_scope_is_rejected():
    """A phase is a phase of the file; one nowhere near the top generates nothing."""
    with pytest.raises(GrammarSyntaxError, match="inside another scope"):
        parse(itemize_text("p Util_ (\n  t Lex (\n    d Int = 0-9\n  )\n)\n"))


def test_a_target_inside_a_target_is_rejected():
    with pytest.raises(GrammarSyntaxError, match="inside another scope"):
        parse(itemize_text("t Outer (\n  d A = a\n  t Inner (\n    d B = b\n  )\n)\n"))
