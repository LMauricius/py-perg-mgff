"""The helpers shared by the generator backends."""

import pytest

from pyperg.mgff.lexer import lex_text
from pyperg.semantics.charset import CHARACTER_SET, parse_character_set
from pyperg.semantics.model import (
    Choice,
    MacroCall,
    Production,
    Reference,
    Repetition,
    Sequence,
)
from pyperg.generators.utils.emit import Emitter
from pyperg.generators.utils.graph import (
    cycles,
    reachable_from,
    recursive_names,
    reference_graph,
    topological_order,
)
from pyperg.generators.utils.naming import NameAllocator, pascal_case, safe_identifier, snake_case
from pyperg.generators.utils.regex import character_class, regex_of
from pyperg.generators.utils.walk import fuse_literals, literal_of, nullable, references
from pyperg.generators.utils.xmlwrite import Element, escape_attribute


def chars(text: str) -> MacroCall:
    """A character-set node, built from the item that spells the set."""
    item = lex_text(text).lines[0].items[0]
    assert parse_character_set(item.text) is not None
    return MacroCall(macro=CHARACTER_SET, item=item)


def production(name: str, *alternatives) -> Production:
    return Production(name=name, alternatives=list(alternatives))


# -- walk -------------------------------------------------------------------


def test_adjacent_single_characters_fuse_into_one_literal():
    # `< =` is two items in MGFF and one string to a matcher.
    fused = fuse_literals([chars("<"), chars("=")])
    assert len(fused) == 1
    assert literal_of(fused[0]) == "<="


def test_fusing_stops_at_anything_that_is_not_one_character():
    fused = fuse_literals([chars("a"), chars("b"), Reference("Rest"), chars("c")])
    assert [literal_of(node) for node in fused] == ["ab", None, "c"]


def test_a_range_is_not_a_literal():
    assert literal_of(chars("0-9")) is None


def test_references_are_reported_in_order():
    rule = Sequence([Reference("A"), Repetition(Reference("B"), 0, None, "*")])
    assert references(rule) == ["A", "B"]


def test_nullability_follows_references():
    table = {"A": production("A", Repetition(chars("a"), 0, None, "*"))}
    assert nullable(Reference("A"), table.get)
    assert not nullable(chars("a"), table.get)


def test_a_cycle_is_not_nullable():
    table = {"A": production("A", Reference("A"))}
    assert not nullable(Reference("A"), table.get)


# -- graph ------------------------------------------------------------------


def test_the_reference_graph_drops_names_outside_the_table():
    table = {
        "A": production("A", Sequence([Reference("B"), Reference("Elsewhere")])),
        "B": production("B", chars("b")),
    }
    assert reference_graph(table) == {"A": ["B"], "B": []}


def test_reachability_follows_the_graph():
    graph = {"File": ["A"], "A": ["B"], "B": [], "Unused": ["A"]}
    assert reachable_from("File", graph) == {"File", "A", "B"}


def test_recursion_is_found_both_direct_and_mutual():
    assert recursive_names({"A": ["A"]}) == {"A"}
    assert recursive_names({"A": ["B"], "B": ["A"]}) == {"A", "B"}
    assert cycles({"A": ["B"], "B": []}) == []


def test_a_topological_order_puts_callees_first():
    order = topological_order({"A": ["B"], "B": ["C"], "C": []})
    assert order.index("C") < order.index("B") < order.index("A")


# -- regex ------------------------------------------------------------------


@pytest.mark.parametrize(
    "text, pattern",
    [
        ("a", "a"),
        ("+", r"\+"),
        ("0-9", "[0-9]"),
        ("a-z|A-Z|_", "[a-zA-Z_]"),
        ("Lu", r"\p{Lu}"),
        ("Lu|_", r"[\p{Lu}_]"),
    ],
)
def test_a_character_set_becomes_a_pattern(text, pattern):
    assert character_class(parse_character_set(text)) == pattern


def test_a_repetition_becomes_a_quantifier():
    rule = Repetition(chars("0-9"), 1, None, "+")
    assert regex_of(rule, lambda name: None) == "[0-9]+"


def test_an_optional_group_is_bracketed_before_its_quantifier():
    rule = Repetition(Sequence([chars("."), chars("a")]), 0, 1, "?")
    assert regex_of(rule, lambda name: None) == "(?:\\.a)?"


def test_a_reference_is_inlined():
    table = {"Digit": production("Digit", chars("0-9"))}
    rule = Repetition(Reference("Digit"), 1, None, "+")
    assert regex_of(rule, table.get) == "[0-9]+"


def test_a_recursive_rule_has_no_regular_form():
    table = {"A": production("A", Sequence([chars("a"), Reference("A")]))}
    assert regex_of(Reference("A"), table.get) is None


def test_a_length_based_choice_puts_the_longest_option_first():
    rule = Choice([chars("<"), Sequence([chars("<"), chars("=")])], "|")
    assert regex_of(rule, lambda name: None) == "(?:<=|<)"


def test_an_order_based_choice_keeps_the_written_order():
    rule = Choice([chars("<"), Sequence([chars("<"), chars("=")])], "/")
    assert regex_of(rule, lambda name: None) == "(?:<|<=)"


# -- naming -----------------------------------------------------------------


def test_punctuation_is_spelled_out_in_an_identifier():
    assert safe_identifier("+") == "Plus"
    assert safe_identifier("<=") == "LessEquals"
    assert safe_identifier("Util_pair") == "Util_pair"


def test_a_name_that_would_start_with_a_digit_is_prefixed():
    assert safe_identifier("2big") == "Rule_2big"


def test_case_conversions():
    assert pascal_case("assign-list") == "AssignList"
    assert snake_case("AssignList") == "assign_list"


def test_an_allocator_keeps_names_unique_and_stable():
    allocator = NameAllocator()
    assert allocator.allocate("Rule") == "Rule"
    assert allocator.allocate("Rule") == "Rule2"
    assert allocator.allocate("Rule", key="k") == "Rule3"
    assert allocator.allocate("Anything", key="k") == "Rule3"


# -- xml --------------------------------------------------------------------


def test_an_empty_element_is_written_short():
    assert Element("DetectSpaces").render() == "<DetectSpaces/>\n"


def test_children_are_indented():
    root = Element("contexts")
    root.child("context", name="File")
    assert root.render() == '<contexts>\n  <context name="File"/>\n</contexts>\n'


def test_an_omitted_attribute_is_left_out():
    root = Element("rule")
    child = root.child("DetectChar", char="(", context=None)
    assert "context" not in child.attributes


def test_attribute_values_are_escaped():
    assert escape_attribute('a<b&c"d') == "a&lt;b&amp;c&quot;d"
    assert escape_attribute("\t") == "&#9;"


def test_text_is_escaped_and_kept_on_one_line():
    element = Element("list")
    element.leaf("item", "a<b")
    assert element.render() == "<list>\n  <item>a&lt;b</item>\n</list>\n"


# -- emit -------------------------------------------------------------------


def test_the_emitter_tracks_depth():
    out = Emitter()
    out.line("a")
    with out.nested():
        out.line("b")
        out.line()
    out.line("c")
    assert out.render() == "a\n  b\n\nc\n"
