"""Part 3: pattern macros, character sets, expansion and the resolved model."""

import re
from pathlib import Path

import pytest

from pyperg.diagnostics.errors import SemanticError
from pyperg.mgff.semantics.expand import substitute_parameters
from pyperg.mgff.semantics.macros import ScopeLookupPoint
from pyperg.mgff.itemizing.cst import render_item, signature_of
from pyperg.mgff.itemizing.itemizer import itemize_text
from pyperg.mgff.common.order import rule_tree_macro_order
from pyperg.mgff.common.categories import is_category_name
from pyperg.mgff.common.characters import CHARACTER_PATTERN, CHARACTER_SET_PATTERN
from pyperg.mgff.common.charset import parse_character_set
from pyperg.mgff.common.rules import Choice, MacroCall, Reference, Repetition, Sequence
from pyperg.mgff.systems.model import parse, rule_tree_factory, resolve

def fixture_text(name: str) -> str:
    return (Path(__file__).parent / "fixtures" / name).read_text(encoding="utf-8")


def model_from_text(text: str, name: str = "<test>"):
    fileScope = parse(itemize_text(text, name), rule_tree_factory)
    return resolve(fileScope, name, rule_tree_macro_order())


def first_item(text: str):
    """The single item of a one-item line, for the shape tests."""
    return itemize_text(text).lines[0].items[0]


# -- character sets ---------------------------------------------------------


@pytest.mark.parametrize(
    "text, kinds",
    [
        ("a", ["character"]),
        ("0-9", ["range"]),
        ("a-z|A-Z|_", ["range", "range", "character"]),
        ("Lu|Decimal_Number", ["category", "category"]),
        ("Letter", ["category"]),
    ],
)
def test_a_character_set_reads_its_parts(text, kinds):
    characters = parse_character_set(text)
    assert characters is not None
    assert [part.kind for part in characters.parts] == kinds


@pytest.mark.parametrize("text", ["Digit", "abc", "a-", "Nonsense_Category", ""])
def test_text_that_is_no_character_set_is_rejected(text):
    assert parse_character_set(text) is None


# The separator is a character too, and no escape says which role a `|` plays.
# No part being empty is what decides, so each of these has one reading only.
@pytest.mark.parametrize(
    "text, parts",
    [
        ("|", [("character", "|", "")]),
        ("a||", [("character", "a", ""), ("character", "|", "")]),
        ("||a", [("character", "|", ""), ("character", "a", "")]),
        ("a|||b", [("character", "a", ""), ("character", "|", ""), ("character", "b", "")]),
        ("|-~", [("range", "|", "~")]),
        ("!-|", [("range", "!", "|")]),
    ],
)
def test_the_separator_is_a_character_where_no_part_may_be_empty(text, parts):
    characters = parse_character_set(text)
    assert characters is not None
    assert [(p.kind, p.value, p.high) for p in characters.parts] == parts


@pytest.mark.parametrize("text", ["||", "|a-", "a|"])
def test_text_leaving_an_empty_part_is_no_character_set(text):
    assert parse_character_set(text) is None


@pytest.mark.parametrize("text", ["a", "|", "0-9", "|-~", "Lu", "9-0"])
def test_the_character_shape_matches_what_one_part_may_be(text):
    # The shapes are matched against a signature and must accept exactly the
    # text the reader accepts, save for `9-0`, which the reader declines.
    assert re.fullmatch(CHARACTER_PATTERN, text)
    assert not re.fullmatch(CHARACTER_SET_PATTERN, text)


@pytest.mark.parametrize("text", ["a|b", "a||", "||a", "a-z|A-Z|_", "Lu|Decimal_Number"])
def test_the_character_set_shape_matches_sets_of_several_parts(text):
    assert re.fullmatch(CHARACTER_SET_PATTERN, text)
    assert not re.fullmatch(CHARACTER_PATTERN, text)


def test_one_letter_abbreviations_are_not_category_names():
    # A single character is already a character part, so `L` cannot be a category.
    assert not is_category_name("L")
    assert is_category_name("Letter")
    assert is_category_name("Lu")


def test_a_category_matches_by_unicode_class():
    characters = parse_character_set("Lu|_")
    assert characters is not None
    assert characters.matches("A")
    assert characters.matches("_")
    assert not characters.matches("a")


def test_a_range_matches_inclusively():
    characters = parse_character_set("0-9")
    assert characters is not None
    assert characters.matches("0") and characters.matches("9")
    assert not characters.matches("a")


# -- pattern macros ---------------------------------------------------------


def shape_names_matching(text: str) -> list[str]:
    """The macros whose shape fits an item, in the order they are tried.

    A `ScopeLookupPoint` place in the order is named for what it consults, since which
    definition is found there is a question for the scope.
    """
    signature = signature_of(first_item(text))
    return [
        macro.shape.name
        for macro in rule_tree_macro_order()
        if macro.shape.match(signature) is not None
    ]


@pytest.mark.parametrize(
    "text, shape",
    [
        ("( a b )", "subgroup"),
        ("( Digit )+", "repetition"),
        ("( Digit )*", "repetition"),
        ("( Digit )?", "repetition"),
        ("(+)/(-)", "choice"),
        ("(a)|(b)|(c)", "choice"),
        ("sep(x)by(y)", "name-with-arguments"),
        ("a-z|A-Z", "character-set"),
        ("Digit", "name"),
    ],
)
def test_an_item_is_read_by_the_first_macro_its_shape_fits(text, shape):
    assert shape_names_matching(text)[0] == shape


def test_a_multi_part_set_outranks_a_production_of_the_same_name():
    # Nothing is tried before it, so no definition of `a-z|A-Z` can win.
    assert shape_names_matching("a-z|A-Z")[0] == "character-set"


def test_a_single_part_set_yields_to_a_production_of_the_same_name():
    # The set is reached only when the scope has no definition of that name.
    assert shape_names_matching("Letter") == ["name", "character"]


def test_the_grammars_own_definitions_are_consulted_at_two_places():
    order = rule_tree_macro_order()
    scope_lookup_shape_names = [
        macro.shape.name for macro in order if isinstance(macro, ScopeLookupPoint)
    ]
    assert scope_lookup_shape_names == ["name-with-arguments", "name"]


def test_a_signature_escapes_text_that_spells_a_group():
    # `\(\)` is two characters, and must not read as an empty group.
    assert signature_of(first_item(r"\(\)")) == r"\(\)"
    assert shape_names_matching(r"\(\)")[0] == "name"


def test_a_choice_may_not_mix_its_separators():
    assert "choice" not in shape_names_matching("(a)|(b)/(c)")
    with pytest.raises(SemanticError, match="unknown name"):
        model_from_text("t Lex (\n d Sign = (a)|(b)/(c)\n)")


# -- resolution -------------------------------------------------------------


def test_the_example_grammar_resolves():
    model = model_from_text(fixture_text("calc.mgff"), "calc.mgff")
    assert [target.name for target in model.targets] == ["Lex", "Parse"]


def test_a_repetition_keeps_its_bounds():
    model = model_from_text("t Lex (\n d Int = ( 0-9 )+\n)")
    rule = model.target("Lex").productions["Int"].rule
    assert isinstance(rule, Repetition)
    assert (rule.minimum, rule.maximum, rule.marker) == (1, None, "+")


def test_an_inline_choice_keeps_its_preference_mode():
    model = model_from_text("t Lex (\n d Sign = (+)/(-)\n)")
    rule = model.target("Lex").productions["Sign"].rule
    assert isinstance(rule, Choice) and rule.symbol == "/"
    assert all(isinstance(option, MacroCall) for option in rule.options)


def test_alternatives_are_kept_in_order_with_their_marker():
    model = model_from_text("t Lex (\n d Op = <\n | =\n)")
    production = model.target("Lex").productions["Op"]
    assert production.choice_symbol == "|"
    assert len(production.alternatives) == 2


def test_a_call_becomes_a_reference_rather_than_an_expansion():
    model = model_from_text("t Lex (\n d Digit = 0-9\n d Int = ( Digit )+\n)")
    rule = model.target("Lex").productions["Int"].rule
    assert isinstance(rule, Repetition)
    assert rule.body == Reference("Digit")


def test_a_recursive_production_resolves_without_looping():
    model = model_from_text("t Parse (\n d Expr = Expr + Expr\n / a\n)")
    assert "Expr" in model.target("Parse").productions


def test_a_mixfix_call_is_expanded_in_place():
    text = "d sep(R)by(S) = R (S R)*\nt Parse (\n d List = sep(a)by(,)\n)"
    rule = model_from_text(text).target("Parse").productions["List"].rule
    # a ( , a )*
    assert isinstance(rule, Sequence)
    assert isinstance(rule.items[0], MacroCall)
    assert isinstance(rule.items[1], Repetition)


def test_a_call_of_the_wrong_shape_finds_no_macro():
    # A call is looked up by signature, so `sep()` never reaches `sep()by()`;
    # a missing slot is a missing name rather than a wrong argument count.
    text = "d sep(R)by(S) = R (S R)*\nt Parse (\n d List = sep(a)\n)"
    with pytest.raises(SemanticError, match="unknown name"):
        model_from_text(text)


def test_a_parameter_is_substituted_by_its_argument():
    # The shape binds a call's arguments to the parameters, so expansion is
    # substitution alone and has no arity left to check.
    body = itemize_text("R (S R)*").lines[0].items
    argument = itemize_text("a").lines[0].items
    expanded = substitute_parameters(body, {"R": argument})
    assert " ".join(render_item(item) for item in expanded) == "a (S a)*"


def test_an_unknown_name_is_reported():
    with pytest.raises(SemanticError, match="unknown name"):
        model_from_text("t Parse (\n d Expr = Undefined\n)")


def test_a_later_target_may_call_an_earlier_one():
    text = "t Lex (\n d Ident = a-z\n)\nt Parse (\n d Expr = Ident\n)"
    parse_target = model_from_text(text).target("Parse")
    assert parse_target.productions["Ident"].origin == "Lex"


def test_a_prefix_scope_keeps_its_prefix_in_the_production_name():
    text = "t Lex (\n p Util_ (\n  d pair = a\n )\n d Main = Util_pair\n)"
    assert "Util_pair" in model_from_text(text).target("Lex").productions


# -- attributes -------------------------------------------------------------


def test_attributes_accumulate_with_their_arguments():
    model = model_from_text("t Lex (\n d Int = 0-9\n > token\n > skip(false)\n)")
    attributes = model.target("Lex").productions["Int"].attributes
    assert attributes == {"token": [], "skip": ["false"]}


def test_an_attribute_only_macro_names_a_list_that_is_spliced_in():
    text = "d Shared > token  class(Keyword)\nt Lex (\n d Int = 0-9\n > Shared\n)"
    attributes = model_from_text(text).target("Lex").productions["Int"].attributes
    assert attributes == {"token": [], "class": ["Keyword"]}


def test_the_attributes_at_the_top_of_a_file_describe_the_grammar():
    model = model_from_text("> name(Toy) section(Sources)\nt Lex (\n d Int = 0-9\n)")
    assert model.attributes == {"name": ["Toy"], "section": ["Sources"]}


def test_the_attributes_at_the_top_of_a_target_describe_the_phase():
    text = (
        "t Lex (\n d Int = 0-9\n)\nt Parse (\n > post(Lex) over(tokens)\n d F = Int\n)"
    )
    model = model_from_text(text)
    assert model.target("Parse").attributes == {"post": ["Lex"], "over": ["tokens"]}
    assert model.target("Lex").attributes == {}


def test_a_scope_may_name_an_attribute_list_of_its_own():
    # A scope's attributes come above its definitions, so the list it names is
    # written below; the reference is followed once the whole file is read.
    text = "> Shared\nd Shared > name(Toy)\nt Lex (\n d Int = 0-9\n)"
    assert model_from_text(text).attributes == {"name": ["Toy"]}


def test_an_attribute_list_that_names_itself_is_reported():
    text = "d Loop > Loop\nt Lex (\n d Int = 0-9\n > Loop\n)"
    with pytest.raises(SemanticError, match="refers to itself"):
        model_from_text(text)


def test_two_attribute_lists_of_one_name_are_two_lists():
    """A splice path is a path through macros; a name is unique only in its scope."""
    model = model_from_text(
        "d A > x\n"
        "d B > A\n"
        "t T (\n"
        "    d C = c\n"
        "      > A\n"
        "    d A > B\n"
        ")\n"
    )
    target = model.target("T")
    assert target is not None
    assert "x" in target.productions["C"].attributes


def test_an_attribute_list_naming_itself_is_still_reported():
    with pytest.raises(SemanticError, match="refers to itself"):
        model_from_text("d A = a\n  > list\nd list > list\n")
