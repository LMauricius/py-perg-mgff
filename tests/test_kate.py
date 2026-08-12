"""The Kate syntax-definition backend."""

import xml.etree.ElementTree as ElementTree
from pathlib import Path

import pytest

from pyperg.diagnostics.errors import GeneratorError
from pyperg.generators.kate import KateGenerator
from pyperg.generators.kate.styles import item_data_for_styles
from pyperg.mgff.itemizing.itemizer import itemize_text
from pyperg.mgff.systems.model import parse, rule_tree_factory, resolve

def fixture_text(name: str) -> str:
    return (Path(__file__).parent / "fixtures" / name).read_text(encoding="utf-8")


def model_of_text(text: str, name: str = "<test>"):
    """Resolve through the backend's own vocabulary, as `generate` does."""
    fileScope = parse(itemize_text(text, name), rule_tree_factory)
    return resolve(fileScope, name, KateGenerator().macros())


def rendered_xml_of(text: str, name: str = "<test>") -> str:
    return KateGenerator().render(model_of_text(text, name))


def xml_tree_of(text: str) -> ElementTree.Element:
    return ElementTree.fromstring(rendered_xml_of(text))


def context_named(root: ElementTree.Element, name: str) -> ElementTree.Element:
    context = root.find(f".//context[@name='{name}']")
    assert context is not None, f"no context named {name}"
    return context


def rule_tags(context: ElementTree.Element) -> list[str]:
    return [child.tag for child in context]


# A `Parse` whose lines carry roles: the marker opens a line, the group holds
# items and nothing else.
MARKED_LINES = """
t Lex (
    d Marker = d
        > style(Keyword)
    d Name = ( a-z|A-Z )+
    d NewLine = \\n
    d File = ( (Marker)/(Name) )*
)

t Parse (
    > post(Lex)
    d Line = Marker Items NewLine
    d Items = ( (Name)/(Group)/(Space) )*
    d Space = ( \\_ )+
    d Group = \\( Items \\)
    d File = ( (Line)/(NewLine) )*
)
"""

ONE_PHASE = """
t Parse (
    d Digit = 0-9
    d Space = ( \\_|\\t )+
    d Int = ( Digit )+
    d File = ( Space / Int )*
)
"""


# -- the fixture end to end -------------------------------------------------


@pytest.fixture(scope="module")
def toy_language_xml() -> ElementTree.Element:
    return ElementTree.fromstring(
        rendered_xml_of(fixture_text("kate.mgff"), "kate.mgff")
    )


def test_the_output_is_well_formed_xml(toy_language_xml):
    assert toy_language_xml.tag == "language"


def test_the_language_describes_itself_from_the_file_attributes(toy_language_xml):
    assert toy_language_xml.get("name") == "Toy"
    assert toy_language_xml.get("extensions") == "*.toy"
    assert toy_language_xml.get("mimetype") == "text/x-toy"
    assert toy_language_xml.get("section") == "Sources"
    assert toy_language_xml.get("kateversion")


def test_the_first_context_is_the_one_a_document_starts_in(toy_language_xml):
    contexts = toy_language_xml.find(".//contexts")
    assert contexts[0].get("name") == "File"


def test_a_run_of_whitespace_becomes_detect_spaces(toy_language_xml):
    assert "DetectSpaces" in rule_tags(context_named(toy_language_xml, "File"))


def test_fixed_words_become_a_keyword_list(toy_language_xml):
    keyword = context_named(toy_language_xml, "File").find("keyword")
    assert keyword is not None
    words = toy_language_xml.find(f".//list[@name='{keyword.get('String')}']")
    assert [item.text for item in words] == ["let", "if", "else", "while"]


def test_two_character_operators_use_detect2chars_and_come_first(toy_language_xml):
    rule_tag_names = rule_tags(context_named(toy_language_xml, "File"))
    assert "Detect2Chars" in rule_tag_names
    # A length-based choice wants the longest match, and Kate takes the first
    # rule that matches, so `<=` must be tried before `<`.
    assert rule_tag_names.index("Detect2Chars") < len(rule_tag_names) - 1


def test_a_single_character_becomes_detect_char(toy_language_xml):
    detected_characters = [
        rule.get("char")
        for rule in context_named(toy_language_xml, "File").findall("DetectChar")
    ]
    assert {"+", "-", "*", "="} <= set(detected_characters)


def test_a_character_range_becomes_an_expression(toy_language_xml):
    patterns = [
        rule.get("String")
        for rule in context_named(toy_language_xml, "File").findall("RegExpr")
    ]
    assert any("[0-9]" in pattern for pattern in patterns)
    assert any("\\p{L}" in pattern for pattern in patterns)


# -- styles -----------------------------------------------------------------


def test_a_style_reaches_kate_as_that_default_style(toy_language_xml):
    style = toy_language_xml.find(".//itemData[@name='Keyword']")
    assert style is not None and style.get("defStyleNum") == "dsKeyword"


def test_a_style_reached_through_a_named_attribute_list(toy_language_xml):
    # `Ident` carries `Classed` for its class and names its own style.
    assert (
        toy_language_xml.find(".//itemData[@name='Variable']").get("defStyleNum")
        == "dsVariable"
    )
    assert (
        toy_language_xml.find(".//itemData[@name='Comment']").get("defStyleNum")
        == "dsComment"
    )


def test_a_class_does_not_reach_the_item_data_name(toy_language_xml):
    """`class(Literal) style(Float)` colours as a float and is called one."""
    assert toy_language_xml.find(".//itemData[@name='Float.Literal']") is None
    assert (
        toy_language_xml.find(".//itemData[@name='Float']").get("defStyleNum")
        == "dsFloat"
    )


def test_a_qualifier_joins_the_item_data_name_and_the_style_colours_it():
    name, default_style = item_data_for_styles(["Keyword", "Control"])
    assert (name, default_style) == ("Keyword.Control", "dsKeyword")


def test_a_style_naming_none_of_the_vocabulary_is_rejected():
    model = model_of_text(
        "t Parse (\n d Digit = 0-9\n > style(Mine)\n d File = ( Digit )*\n)"
    )
    with pytest.raises(GeneratorError, match="is no highlighting style"):
        KateGenerator().render(model)


def test_a_production_naming_no_style_is_left_unstyled(toy_language_xml):
    """Nothing derives a style, so an unstyled match is coloured by its context."""
    assert toy_language_xml.find(".//itemData[@name='Ident']") is None


# -- the Parse target -------------------------------------------------------


def test_a_bracketing_production_becomes_a_context_that_folds(toy_language_xml):
    file_context = context_named(toy_language_xml, "File")
    push = file_context.find("DetectChar[@context='Atom']")
    assert push is not None
    assert push.get("char") == "(" and push.get("beginRegion") == "Atom"

    atom = context_named(toy_language_xml, "Atom")
    assert atom[0].get("char") == ")"
    assert atom[0].get("context") == "#pop" and atom[0].get("endRegion") == "Atom"


def test_the_bracket_rule_is_tried_before_the_token_of_the_same_shape(toy_language_xml):
    tags_and_contexts = [
        (child.tag, child.get("context"))
        for child in context_named(toy_language_xml, "File")
    ]
    # The bracket rule comes first, so `(` opens its context rather than being
    # eaten by a token of the same shape.
    assert tags_and_contexts[0] == ("DetectChar", "Atom")
    assert all(
        context != "Atom"
        for tag, context in tags_and_contexts[1:]
        if tag != "DetectChar"
    )


def test_a_context_holds_what_its_place_in_the_grammar_reaches(toy_language_xml):
    """Strictly: the tokens `Parse` names there, and no others."""
    for name in ("File", "Atom"):
        patterns = [
            rule.get("String")
            for rule in context_named(toy_language_xml, name).findall("RegExpr")
        ]
        assert any("[0-9]" in pattern for pattern in patterns)  # Number
        assert any("\\p{L}" in pattern for pattern in patterns)  # Ident


def test_a_context_the_grammar_does_not_reach_holds_nothing_of_it():
    """A group whose lines hold no definitions holds no `d` rule either."""
    tree = xml_tree_of(MARKED_LINES)
    # A marker spelled as a letter is a `WordDetect`, so the `d` of `Digit`
    # does not open a definition.
    assert context_named(tree, "File").find("WordDetect").get("String") == "d"
    group_context = context_named(tree, "Group")
    assert [rule.get("char") for rule in group_context.findall("DetectChar")] == [
        ")",
        "(",
    ]


# -- a grammar of a single phase --------------------------------------------


def test_a_grammar_of_one_phase_starts_at_its_matches():
    root = xml_tree_of(ONE_PHASE)
    contexts = root.find(".//contexts")
    assert [context.get("name") for context in contexts] == ["Tokens"]


def test_only_the_productions_file_names_become_rules():
    # `Digit` is a helper: it is inlined into `Int`, never tried on its own.
    tokens = context_named(xml_tree_of(ONE_PHASE), "Tokens")
    assert len(tokens) == 2


def test_the_name_falls_back_to_the_grammar_file():
    root = ElementTree.fromstring(rendered_xml_of(ONE_PHASE, "my-toy.mgff"))
    assert root.get("name") == "MyToy"
    assert root.get("extensions") == "*.mytoy"


# -- what the backend refuses ----------------------------------------------


def test_a_target_without_a_file_macro_is_reported():
    with pytest.raises(GeneratorError, match="no `File` macro"):
        rendered_xml_of("t Parse (\n d Int = 0-9\n)")


def test_a_file_macro_naming_no_productions_is_reported():
    with pytest.raises(GeneratorError, match="names no productions"):
        rendered_xml_of("t Parse (\n d File = 0-9\n)")


def test_a_chain_not_ending_at_parse_is_reported():
    with pytest.raises(GeneratorError, match="it has to be 'Parse'"):
        rendered_xml_of("t Other (\n d File = 0-9\n)")


def test_a_recursive_token_cannot_be_matched():
    text = "t Parse (\n d Nested = \\( Nested \\)\n d File = ( Nested )*\n)"
    with pytest.raises(GeneratorError, match="reaches itself"):
        rendered_xml_of(text)


def test_a_target_off_the_chain_is_reported():
    """A phase nothing runs after and that runs after nothing never runs."""
    text = ONE_PHASE + "\nt Other (\n d Thing = a\n)"
    with pytest.raises(GeneratorError, match="all run first"):
        rendered_xml_of(text)


# -- writing ----------------------------------------------------------------


def test_generate_writes_one_file_named_after_the_language(tmp_path):
    model = model_of_text(fixture_text("kate.mgff"), "kate.mgff")
    written_paths = KateGenerator().generate(model, tmp_path)
    assert written_paths == [tmp_path / "Toy.xml"]
    assert written_paths[0].read_text(encoding="utf-8").startswith("<?xml")


# -- what a syntax definition can carry -------------------------------------


def test_a_control_character_is_matched_by_an_expression():
    """XML 1.0 carries no control character, so the literal rules decline one."""
    text = (
        "t Lex (\n"
        "    d File = ( Nul )*\n"
        "    d Nul = \\0\n"
        "      > style(Keyword) class(N) push(t)\n"
        ")\n"
        "t Parse (\n"
        "    > post(Lex) over(t)\n"
        "    d File = ( Nul )*\n"
        ")\n"
    )
    root = xml_tree_of(text)  # parses, which is the whole point
    assert root.find(".//RegExpr[@String='\\x{00}']") is not None
    assert root.find(".//DetectChar") is None


@pytest.mark.parametrize(
    "body, pattern",
    [
        (r"\uFFFE", r"\x{fffe}"),
        (r"\uFFFF", r"\x{ffff}"),
        (r"a|\uFFFE", r"[a\x{fffe}]"),
    ],
)
def test_a_non_character_is_spelled_as_an_escape(body, pattern):
    """XML 1.0 carries U+FFFE and U+FFFF nowhere, so no rule may write one raw."""
    text = (
        "t Lex (\n"
        "    d File = ( Odd )*\n"
        f"    d Odd = {body}\n"
        "      > style(Keyword) class(O) push(t)\n"
        ")\n"
        "t Parse (\n"
        "    > post(Lex) over(t)\n"
        "    d File = ( Odd )*\n"
        ")\n"
    )
    root = xml_tree_of(text)  # parses, which is the whole point
    assert root.find(f".//RegExpr[@String='{pattern}']") is not None


def test_a_token_matching_nothing_is_left_out(capsys):
    """A zero-width rule colours nothing however often a context tries it."""
    text = "t Parse (\n    d File = ( E )*\n    d E =\n      > style(Keyword)\n)\n"
    root = xml_tree_of(text)
    assert root.find(".//RegExpr") is None
    assert "can match the empty string" in capsys.readouterr().err


def test_the_grammars_name_names_a_file_and_not_a_path(tmp_path):
    """A grammar names itself, and that name may not leave the output directory."""
    text = (
        "> name(../../pwned)\n"
        "t Parse (\n"
        "    d File = ( A )*\n"
        "    d A = a\n"
        "      > style(Keyword)\n"
        ")\n"
    )
    out_dir = tmp_path / "out"
    written_paths = KateGenerator().generate(model_of_text(text), out_dir)
    assert [path.parent for path in written_paths] == [out_dir]
    assert not list(tmp_path.parent.glob("pwned*"))
