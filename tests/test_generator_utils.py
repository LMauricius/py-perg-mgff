"""The helpers shared by the generator backends."""

import pytest

from pyperg.mgff.lexing.lexer import lex_text
from pyperg.mgff.common.characters import CHARACTER_SET
from pyperg.mgff.common.charset import parse_character_set
from pyperg.mgff.common.rules import Choice, MacroCall, Reference, Repetition, Sequence
from pyperg.mgff.common.order import rule_tree_macros
from pyperg.mgff.semantics.model import Production, resolve
from pyperg.diagnostics.errors import GeneratorError
from pyperg.generators.utils.classes import classes_of
from pyperg.generators.utils.pipeline import resolve_over, stages_of
from pyperg.generators.utils.emit import Emitter
from pyperg.generators.utils.naming import safe_file_name
from pyperg.generators.utils.graph import (
    cycles,
    reachable_from,
    recursive_names,
    reference_graph,
    topological_order,
)
from pyperg.generators.utils.naming import NameAllocator, pascal_case, safe_identifier, snake_case
from pyperg.generators.utils.regex import alternation, character_class, regex_of
from pyperg.generators.utils.styles import styles_of
from pyperg.generators.utils.walk import fuse_literals, literal_of, nullable, references, rewrite
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


def test_an_escaped_metacharacter_is_measured_as_the_character_it_is():
    # `\+` is a literal `+`, so `++` is the longer option and has to come first.
    rule = Choice([chars("+"), Sequence([chars("+"), chars("+")])], "|")
    assert regex_of(rule, lambda name: None) == r"(?:\+\+|\+)"


def test_options_of_the_same_length_keep_the_written_order():
    assert alternation([r"\+", "-", r"\*", "="], "|") == r"(?:\+|-|\*|=)"


@pytest.mark.parametrize(
    "options, ordered",
    [
        # A character class matches one character, however many it lists.
        (["[+*]", "ab"], "(?:ab|[+*])"),
        # So does a Unicode category, however long its name.
        ([r"\p{Lu}", "ab"], r"(?:ab|\p{Lu})"),
        # A quantifier, an alternation and a group have no fixed length at all.
        # Every option that has one is tried ahead of them, whichever way round
        # they were written: a variable-length option would otherwise match
        # short and take the whole choice with it.
        (["ab", "c+"], "(?:ab|c+)"),
        (["c+", "ab"], "(?:ab|c+)"),
        (["(?:xy)", "ab"], "(?:ab|(?:xy))"),
    ],
)
def test_a_length_based_choice_measures_what_it_can(options, ordered):
    assert alternation(options, "|") == ordered


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


# -- classes and styles -----------------------------------------------------


def labelled(name: str, **attributes) -> Production:
    """A production carrying nothing but its name and its attributes."""
    return Production(name=name, attributes=dict(attributes))


def test_a_class_is_kept_exactly_as_it_was_written():
    """Classes are free text: a later phase matches its terminals against them."""
    assert classes_of(labelled("LParen", **{"class": ["\\("]})) == ["\\("]
    assert classes_of(labelled("Number", **{"class": ["Float", "Literal"]})) == [
        "Float",
        "Literal",
    ]


def test_autoclass_is_the_macros_own_name():
    assert classes_of(labelled("Comment", autoclass=[])) == ["Comment"]


def test_a_production_asking_for_no_class_has_none():
    assert classes_of(labelled("Space")) == []


def test_an_empty_class_is_reported():
    with pytest.raises(GeneratorError, match="needs at least one class"):
        classes_of(labelled("Int", **{"class": []}))


def test_a_style_is_the_vocabulary_plus_its_qualifiers():
    assert styles_of(labelled("Op", style=["Operator"])) == ["Operator"]
    assert styles_of(labelled("If", style=["Keyword", "Control"])) == [
        "Keyword",
        "Control",
    ]


def test_a_production_asking_for_no_style_is_unstyled():
    """Nothing is derived from a name, so an unstyled match stays unstyled."""
    assert styles_of(labelled("Comment")) == []


def test_a_style_outside_the_vocabulary_is_reported():
    with pytest.raises(GeneratorError, match="is no highlighting style"):
        styles_of(labelled("Int", style=["Mine"]))
    with pytest.raises(GeneratorError, match="needs a style"):
        styles_of(labelled("Int", style=[]))


def test_only_the_first_name_of_a_style_has_to_be_known():
    assert styles_of(labelled("If", style=["Keyword", "Mine"])) == ["Keyword", "Mine"]


# -- the pipeline -----------------------------------------------------------

#: Two phases: one that reads text and pushes what it matched, one that reads
#: the list. `LParen` answers to the class `\(`, which is how `Parse` names it.
TWO_PHASES = """
t Lex (
    d Digit = 0-9
    d Number = ( Digit )+
        > class(Number) style(Float) push(tokens)
    d LParen = \\(
        > class(\\() style(Normal) push(tokens)
    d RParen = \\)
        > class(\\)) style(Normal) push(tokens)
    d File = ( (Number)/(LParen)/(RParen) )*
)

t Parse (
    > post(Lex) over(tokens)
    d Group = \\( Number \\)
    d File = ( (Group)/(Number) )*
)
"""


def staged(text: str):
    """The phases of a grammar, with every `over` already resolved."""
    model = resolve(lex_text(text, "<test>"), "<test>", rule_tree_macros())
    stages = stages_of(model)
    for stage in stages:
        resolve_over(stage)
    return model, stages


def test_the_phases_come_out_in_the_order_post_puts_them_in():
    _, stages = staged(TWO_PHASES)
    assert [stage.target.name for stage in stages] == ["Lex", "Parse"]
    assert stages[0].matches_characters and not stages[1].matches_characters
    assert stages[1].previous is stages[0]


def test_a_terminal_of_an_over_phase_becomes_a_call_on_the_match_it_names():
    _, stages = staged(TWO_PHASES)
    group = stages[1].target.productions["Group"]
    # `\( Number \)` now calls the productions carrying those classes.
    assert references(group.rule) == ["LParen", "Number", "RParen"]
    # And they are in this phase's table, since it references them now.
    assert "LParen" in stages[1].target.productions


def test_a_production_reached_by_name_keeps_matching_its_own_characters():
    """`Number` was pulled in by reference, not by class; its set stays a set."""
    _, stages = staged(TWO_PHASES)
    assert references(stages[1].target.productions["Number"].rule) == ["Digit"]


def test_a_class_nothing_pushes_is_reported():
    text = TWO_PHASES.replace("> class(\\() style(Normal) push(tokens)", "> style(Normal)")
    with pytest.raises(GeneratorError, match="nothing pushed to 'tokens'"):
        staged(text)


def test_a_set_of_characters_means_nothing_over_a_list():
    text = TWO_PHASES.replace("d Group = \\( Number \\)", "d Group = a-z")
    with pytest.raises(GeneratorError, match="names nothing there"):
        staged(text)


def test_over_without_a_phase_before_it_is_reported():
    text = "t Parse (\n > over(tokens)\n d File = 0-9\n)"
    with pytest.raises(GeneratorError, match="runs first"):
        staged(text)


def test_a_phase_running_after_a_target_that_is_not_there_is_reported():
    text = "t Parse (\n > post(Nowhere)\n d File = 0-9\n)"
    with pytest.raises(GeneratorError, match="no target called 'Nowhere'"):
        staged(text)


def test_two_phases_running_after_the_same_one_are_reported():
    text = (
        "t Lex (\n d File = 0-9\n)\n"
        "t Mid (\n > post(Lex)\n d File = 0-9\n)\n"
        "t Parse (\n > post(Lex)\n d File = 0-9\n)"
    )
    with pytest.raises(GeneratorError, match="a chain, not a tree"):
        staged(text)


def test_a_cycle_leaves_the_chain_without_a_beginning():
    text = (
        "t Lex (\n > post(Parse)\n d File = 0-9\n)\n"
        "t Parse (\n > post(Lex)\n d File = 0-9\n)"
    )
    with pytest.raises(GeneratorError, match="no beginning"):
        staged(text)


# -- rewriting rule trees ---------------------------------------------------


def test_a_rewrite_replaces_a_node_without_walking_into_what_replaces_it():
    tree = Sequence([Reference("a"), Repetition(Reference("b"), 0, None, "*")])
    swapped = rewrite(tree, lambda node: Reference("c") if node == Reference("b") else None)
    assert references(swapped) == ["a", "c"]
    # The original is untouched: a rewrite builds a new tree.
    assert references(tree) == ["a", "b"]


# -- names that reach the file system ---------------------------------------


@pytest.mark.parametrize(
    "name, expected",
    [
        ("../../pwned", "pwned"),
        ("/etc/passwd", "etcpasswd"),
        ("My.Toy-1", "My.Toy-1"),
        ("..", "grammar"),
        ("", "grammar"),
    ],
)
def test_a_file_name_can_only_name_a_file(name, expected):
    """A grammar names itself, and that name may not become a path."""
    assert safe_file_name(name) == expected
