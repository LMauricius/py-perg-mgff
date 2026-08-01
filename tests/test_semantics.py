"""Part 3: item shapes, character sets, expansion and the resolved model."""

from pathlib import Path

import pytest

from pyperg.diagnostics.errors import SemanticError
from pyperg.grammar.expand import expand_call
from pyperg.grammar.parser import parse
from pyperg.mgff.lexer import lex_text
from pyperg.semantics.charset import is_category_name, parse_character_set
from pyperg.semantics.model import (
    Chars,
    Choice,
    Reference,
    Repetition,
    Sequence,
    resolve,
)
from pyperg.semantics.shapes import Shape, classify


def read_fixture(name: str) -> str:
    return (Path(__file__).parent / "fixtures" / name).read_text(encoding="utf-8")


def model_of(text: str, name: str = "<test>"):
    return resolve(parse(lex_text(text, name)), name)


def first_item(text: str):
    """The single item of a one-item line, for the shape tests."""
    return lex_text(text).lines[0].items[0]


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


# -- item shapes ------------------------------------------------------------


@pytest.mark.parametrize(
    "text, shape",
    [
        ("( a b )", Shape.SUBGROUP),
        ("( Digit )+", Shape.REPETITION),
        ("( Digit )*", Shape.REPETITION),
        ("( Digit )?", Shape.REPETITION),
        ("(+)/(-)", Shape.CHOICE),
        ("(a)|(b)|(c)", Shape.CHOICE),
        ("sep(x)by(y)", Shape.CALL_WITH_ARGUMENTS),
        ("a-z|A-Z", Shape.CHARACTER_SET),
        ("Digit", Shape.CALL),
    ],
)
def test_an_item_is_read_by_its_shape(text, shape):
    assert classify(first_item(text), character_sets_allowed=True) is shape


def test_a_multi_part_set_outranks_a_production_of_the_same_name():
    item = first_item("a-z|A-Z")
    assert classify(item, True, resolves=lambda name: True) is Shape.CHARACTER_SET


def test_a_single_part_set_yields_to_a_production_of_the_same_name():
    item = first_item("Letter")
    assert classify(item, True, resolves=lambda name: True) is Shape.CALL
    assert classify(item, True, resolves=lambda name: False) is Shape.CHARACTER_SET


def test_a_choice_may_not_mix_its_separators():
    assert classify(first_item("(a)|(b)/(c)"), True) is Shape.CALL_WITH_ARGUMENTS


# -- resolution -------------------------------------------------------------


def test_the_example_grammar_resolves():
    model = model_of(read_fixture("calc.mgff"), "calc.mgff")
    assert [target.name for target in model.targets] == ["Lex", "Parse"]
    assert model.target("Lex").matches_characters
    assert not model.target("Parse").matches_characters


def test_a_repetition_keeps_its_bounds():
    model = model_of("t Lex (\n d Int = ( 0-9 )+\n)")
    rule = model.target("Lex").productions["Int"].rule
    assert isinstance(rule, Repetition)
    assert (rule.minimum, rule.maximum, rule.marker) == (1, None, "+")


def test_an_inline_choice_keeps_its_preference_mode():
    model = model_of("t Lex (\n d Sign = (+)/(-)\n)")
    rule = model.target("Lex").productions["Sign"].rule
    assert isinstance(rule, Choice) and rule.symbol == "/"
    assert all(isinstance(option, Chars) for option in rule.options)


def test_alternatives_are_kept_in_order_with_their_marker():
    model = model_of("t Lex (\n d Op = <\n | =\n)")
    production = model.target("Lex").productions["Op"]
    assert production.choice_symbol == "|"
    assert len(production.alternatives) == 2


def test_a_call_becomes_a_reference_rather_than_an_expansion():
    model = model_of("t Lex (\n d Digit = 0-9\n d Int = ( Digit )+\n)")
    rule = model.target("Lex").productions["Int"].rule
    assert isinstance(rule, Repetition)
    assert rule.body == Reference("Digit")


def test_a_recursive_production_resolves_without_looping():
    model = model_of("t Parse (\n d Expr = Expr + Expr\n / a\n)")
    assert "Expr" in model.target("Parse").productions


def test_a_mixfix_call_is_expanded_in_place():
    text = "d sep(R)by(S) = R (S R)*\nt Parse (\n d List = sep(a)by(,)\n)"
    rule = model_of(text).target("Parse").productions["List"].rule
    # a ( , a )*
    assert isinstance(rule, Sequence)
    assert isinstance(rule.items[0], Chars)
    assert isinstance(rule.items[1], Repetition)


def test_a_call_of_the_wrong_shape_finds_no_macro():
    # A call is looked up by signature, so `sep()` never reaches `sep()by()`;
    # a missing slot is a missing name rather than a wrong argument count.
    text = "d sep(R)by(S) = R (S R)*\nt Parse (\n d List = sep(a)\n)"
    with pytest.raises(SemanticError, match="unknown name"):
        model_of(text)


def test_expanding_with_the_wrong_number_of_arguments_is_reported():
    scope = parse(lex_text("d sep(R)by(S) = R (S R)*"))
    macro = scope.lookup("sep()by()")
    with pytest.raises(SemanticError, match="takes 2 argument"):
        expand_call(macro, [[]])


def test_an_unknown_name_is_reported():
    with pytest.raises(SemanticError, match="unknown name"):
        model_of("t Parse (\n d Expr = Undefined\n)")


def test_a_later_target_may_call_an_earlier_one():
    text = "t Lex (\n d Ident = a-z\n)\nt Parse (\n d Expr = Ident\n)"
    parse_target = model_of(text).target("Parse")
    assert parse_target.productions["Ident"].origin == "Lex"


def test_a_prefix_scope_keeps_its_prefix_in_the_production_name():
    text = "t Lex (\n p Util_ (\n  d pair = a\n )\n d Main = Util_pair\n)"
    assert "Util_pair" in model_of(text).target("Lex").productions


# -- attributes -------------------------------------------------------------


def test_attributes_accumulate_with_their_arguments():
    model = model_of("t Lex (\n d Int = 0-9\n > token\n > skip(false)\n)")
    attributes = model.target("Lex").productions["Int"].attributes
    assert attributes == {"token": [], "skip": ["false"]}


def test_an_attribute_only_macro_names_a_list_that_is_spliced_in():
    text = "d Shared > token  class(Keyword)\nt Lex (\n d Int = 0-9\n > Shared\n)"
    attributes = model_of(text).target("Lex").productions["Int"].attributes
    assert attributes == {"token": [], "class": ["Keyword"]}


def test_a_file_scope_attribute_list_is_kept_as_metadata():
    model = model_of("d Language > name(Toy)\nt Lex (\n d Int = 0-9\n)")
    assert model.metadata["Language"] == {"name": ["Toy"]}


def test_an_attribute_list_that_names_itself_is_reported():
    text = "d Loop > Loop\nt Lex (\n d Int = 0-9\n > Loop\n)"
    with pytest.raises(SemanticError, match="refers to itself"):
        model_of(text)
