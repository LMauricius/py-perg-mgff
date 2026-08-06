"""The Kate syntax-definition backend."""

import xml.etree.ElementTree as ElementTree
from pathlib import Path

import pytest

from pyperg.diagnostics.errors import GeneratorError
from pyperg.generators.kate import KateGenerator
from pyperg.generators.kate.styles import autoclass_for, style_for
from pyperg.mgff.lexing.lexer import lex_text
from pyperg.mgff.semantics.model import resolve

def read_fixture(name: str) -> str:
    return (Path(__file__).parent / "fixtures" / name).read_text(encoding="utf-8")


def _model(text: str, name: str = "<test>"):
    """Resolve through the backend's own vocabulary, as `generate` does."""
    return resolve(lex_text(text, name), name, KateGenerator().macros())


def render(text: str, name: str = "<test>") -> str:
    return KateGenerator().render(_model(text, name))


def tree_of(text: str) -> ElementTree.Element:
    return ElementTree.fromstring(render(text))


def context_named(root: ElementTree.Element, name: str) -> ElementTree.Element:
    found = root.find(f".//context[@name='{name}']")
    assert found is not None, f"no context named {name}"
    return found


def rule_tags(context: ElementTree.Element) -> list[str]:
    return [child.tag for child in context]


# A `Parse` whose lines carry roles: the marker opens a line, the group holds
# items and nothing else.
MARKED_LINES = """
t Lex (
    d Marker = d
        > class(Keyword)
    d Name = ( a-z|A-Z )+
    d NewLine = \\n
    d File = ( (Marker)/(Name) )*
)

t Parse (
    d Line = Marker Items NewLine
    d Items = ( (Name)/(Group)/(Space) )*
    d Space = ( \\_ )+
    d Group = \\( Items \\)
    d File = ( (Line)/(NewLine) )*
)
"""

LEX_ONLY = """
t Lex (
    d Digit = 0-9
    d Space = ( \\_|\\t )+
    d Int = ( Digit )+
    d File = ( Space / Int )*
)
"""


# -- the fixture end to end -------------------------------------------------


@pytest.fixture(scope="module")
def toy() -> ElementTree.Element:
    return ElementTree.fromstring(render(read_fixture("kate.mgff"), "kate.mgff"))


def test_the_output_is_well_formed_xml(toy):
    assert toy.tag == "language"


def test_the_language_describes_itself_from_the_file_attributes(toy):
    assert toy.get("name") == "Toy"
    assert toy.get("extensions") == "*.toy"
    assert toy.get("mimetype") == "text/x-toy"
    assert toy.get("section") == "Sources"
    assert toy.get("kateversion")


def test_the_first_context_is_the_one_a_document_starts_in(toy):
    contexts = toy.find(".//contexts")
    assert contexts[0].get("name") == "File"


def test_a_run_of_whitespace_becomes_detect_spaces(toy):
    assert "DetectSpaces" in rule_tags(context_named(toy, "File"))


def test_fixed_words_become_a_keyword_list(toy):
    keyword = context_named(toy, "File").find("keyword")
    assert keyword is not None
    words = toy.find(f".//list[@name='{keyword.get('String')}']")
    assert [item.text for item in words] == ["let", "if", "else", "while"]


def test_two_character_operators_use_detect2chars_and_come_first(toy):
    tags = rule_tags(context_named(toy, "File"))
    assert "Detect2Chars" in tags
    # A length-based choice wants the longest match, and Kate takes the first
    # rule that matches, so `<=` must be tried before `<`.
    assert tags.index("Detect2Chars") < len(tags) - 1


def test_a_single_character_becomes_detect_char(toy):
    chars = [
        rule.get("char")
        for rule in context_named(toy, "File").findall("DetectChar")
    ]
    assert {"+", "-", "*", "="} <= set(chars)


def test_a_character_range_becomes_an_expression(toy):
    patterns = [
        rule.get("String") for rule in context_named(toy, "File").findall("RegExpr")
    ]
    assert any("[0-9]" in pattern for pattern in patterns)
    assert any("\\p{L}" in pattern for pattern in patterns)


# -- classes ----------------------------------------------------------------


def test_an_explicit_class_reaches_kate_as_that_default_style(toy):
    style = toy.find(".//itemData[@name='Keyword']")
    assert style is not None and style.get("defStyleNum") == "dsKeyword"


def test_several_classes_join_the_name_and_the_first_known_one_styles_it(toy):
    style = toy.find(".//itemData[@name='Float.Literal']")
    assert style is not None and style.get("defStyleNum") == "dsFloat"


def test_autoclass_derives_the_style_from_the_macro_name(toy):
    # `Comment` names a default style outright; `Ident` reaches `Variable`
    # through the synonym table, and does so via a named attribute list.
    assert toy.find(".//itemData[@name='Comment']").get("defStyleNum") == "dsComment"
    assert toy.find(".//itemData[@name='Variable']").get("defStyleNum") == "dsVariable"


@pytest.mark.parametrize(
    "macro, style",
    [
        ("Keyword", "Keyword"),
        ("comment", "Comment"),
        ("Ident", "Variable"),
        ("Number", "DecVal"),
        ("HexNumber", "DecVal"),
        ("Hex", "BaseN"),
        ("LineComment", "Comment"),
        ("Space", "Normal"),
    ],
)
def test_autoclass_derivation(macro, style):
    assert autoclass_for(macro, warn=False) == style


def test_an_unrecognised_name_falls_back_to_normal_with_a_warning(capsys):
    assert autoclass_for("Wibble", warn=True) == "Normal"
    assert "no class matches" in capsys.readouterr().err


def test_an_unknown_class_survives_in_the_item_data_name():
    name, default_style = style_for(["Keyword", "Mine"])
    assert (name, default_style) == ("Keyword.Mine", "dsKeyword")


def test_a_class_naming_no_style_at_all_is_still_normal():
    assert style_for(["Mine"]) == ("Mine", "dsNormal")


# -- the Parse target -------------------------------------------------------


def test_a_bracketing_production_becomes_a_context_that_folds(toy):
    grammar = context_named(toy, "File")
    push = grammar.find("DetectChar[@context='Atom']")
    assert push is not None
    assert push.get("char") == "(" and push.get("beginRegion") == "Atom"

    atom = context_named(toy, "Atom")
    assert atom[0].get("char") == ")"
    assert atom[0].get("context") == "#pop" and atom[0].get("endRegion") == "Atom"


def test_the_bracket_rule_is_tried_before_the_token_of_the_same_shape(toy):
    tags = [(child.tag, child.get("context")) for child in context_named(toy, "File")]
    # The bracket rule comes first, so `(` opens its context rather than being
    # eaten by a token of the same shape.
    assert tags[0] == ("DetectChar", "Atom")
    assert all(context != "Atom" for tag, context in tags[1:] if tag != "DetectChar")


def test_a_context_holds_what_its_place_in_the_grammar_reaches(toy):
    """Strictly: the tokens `Parse` names there, and no others."""
    for name in ("File", "Atom"):
        patterns = [rule.get("String") for rule in context_named(toy, name).findall("RegExpr")]
        assert any("[0-9]" in pattern for pattern in patterns)  # Number
        assert any("\\p{L}" in pattern for pattern in patterns)  # Ident


def test_a_context_the_grammar_does_not_reach_holds_nothing_of_it():
    """A group whose lines hold no definitions holds no `d` rule either."""
    tree = tree_of(MARKED_LINES)
    # A marker spelled as a letter is a `WordDetect`, so the `d` of `Digit`
    # does not open a definition.
    assert context_named(tree, "File").find("WordDetect").get("String") == "d"
    inner = context_named(tree, "Group")
    assert [rule.get("char") for rule in inner.findall("DetectChar")] == [")", "("]


# -- a grammar with only a Lex target ---------------------------------------


def test_a_lex_only_grammar_starts_at_its_tokens():
    root = tree_of(LEX_ONLY)
    contexts = root.find(".//contexts")
    assert [context.get("name") for context in contexts] == ["Tokens"]


def test_only_the_productions_file_names_become_rules():
    # `Digit` is a helper: it is inlined into `Int`, never tried on its own.
    tokens = context_named(tree_of(LEX_ONLY), "Tokens")
    assert len(tokens) == 2


def test_the_name_falls_back_to_the_grammar_file():
    root = ElementTree.fromstring(render(LEX_ONLY, "my-toy.mgff"))
    assert root.get("name") == "MyToy"
    assert root.get("extensions") == "*.mytoy"


# -- what the backend refuses ----------------------------------------------


def test_a_target_without_a_file_macro_is_reported():
    with pytest.raises(GeneratorError, match="no `File` macro"):
        render("t Lex (\n d Int = 0-9\n)")


def test_a_file_macro_naming_no_productions_is_reported():
    with pytest.raises(GeneratorError, match="names no productions"):
        render("t Lex (\n d File = 0-9\n)")


def test_a_grammar_with_neither_target_is_reported():
    with pytest.raises(GeneratorError, match="no `Lex` or `Parse` target"):
        render("t Other (\n d File = 0-9\n)")


def test_a_recursive_token_cannot_be_matched():
    text = "t Lex (\n d Nested = \\( Nested \\)\n d File = ( Nested )*\n)"
    with pytest.raises(GeneratorError, match="reaches itself"):
        render(text)


def test_an_empty_class_is_reported():
    text = "t Lex (\n d Int = 0-9\n > class\n d File = ( Int )*\n)"
    with pytest.raises(GeneratorError, match="needs at least one class"):
        render(text)


def test_an_ignored_target_is_reported_on_stderr(capsys):
    text = LEX_ONLY + "\nt Other (\n d Thing = a\n)"
    render(text)
    assert "is not generated" in capsys.readouterr().err


# -- writing ----------------------------------------------------------------


def test_generate_writes_one_file_named_after_the_language(tmp_path):
    model = _model(read_fixture("kate.mgff"), "kate.mgff")
    written = KateGenerator().generate(model, tmp_path)
    assert written == [tmp_path / "Toy.xml"]
    assert written[0].read_text(encoding="utf-8").startswith("<?xml")
