"""The TextMate backend."""

import json
from pathlib import Path

import pytest

from pyperg.diagnostics.errors import GeneratorError
from pyperg.generators.textmate import TextMateGenerator
from pyperg.generators.textmate.scopes import scope_for
from pyperg.mgff.itemizing.itemizer import itemize_text
from pyperg.mgff.systems.model import parse, rule_tree_factory, resolve

regex = pytest.importorskip("regex", reason="the generated patterns use \\p{…}")


def fixture_text(name: str) -> str:
    return (Path(__file__).parent / "fixtures" / name).read_text(encoding="utf-8")


def model_of_text(text: str, name: str = "<test>"):
    """Resolve through the backend's own vocabulary, as `generate` does."""
    fileScope = parse(itemize_text(text, name), rule_tree_factory)
    return resolve(fileScope, name, TextMateGenerator().macros())


def grammar_of(text: str, name: str = "<test>") -> dict:
    return json.loads(TextMateGenerator().render(model_of_text(text, name)))


def repository_entry(grammar: dict, name: str) -> dict:
    entry = grammar["repository"].get(name)
    assert entry is not None, f"no repository entry named {name}"
    return entry


def included_entry_names(pattern: dict) -> list[str]:
    """The entry names one `patterns` list refers to, in order."""
    return [
        item["include"].lstrip("#")
        for item in pattern["patterns"]
        if "include" in item
    ]


def first_match_in(pattern: str, text: str) -> str | None:
    """What the pattern finds in the text, as VS Code's engine would search for it."""
    match = regex.search(pattern, text)
    return match.group(0) if match else None


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
def toy_grammar() -> dict:
    return grammar_of(fixture_text("textmate.mgff"), "textmate.mgff")


def test_the_grammar_names_itself_and_its_scope(toy_grammar):
    assert toy_grammar["name"] == "Toy"
    assert toy_grammar["scopeName"] == "source.toy"
    assert toy_grammar["fileTypes"] == ["toy"]


def test_a_document_starts_at_the_grammar_repository_entry(toy_grammar):
    assert included_entry_names(toy_grammar) == ["grammar"]


def test_the_grammar_entry_tries_brackets_before_tokens(toy_grammar):
    # `(` must open its own span rather than being eaten by a token of the same
    # shape, and the tokens follow in the order `Lex` names them.
    included_here = included_entry_names(repository_entry(toy_grammar, "grammar"))
    assert included_here[0] == "atom"
    assert set(included_here[1:]) == {
        "comment",
        "keyword",
        "number",
        "ident",
        "space",
        "op",
    }


def test_every_token_a_context_reaches_becomes_an_entry_of_its_own(toy_grammar):
    # One entry per token, included where it is reachable, rather than the same
    # expression written out in every context that can reach it.
    for name in ("space", "comment", "keyword", "number", "ident", "op"):
        assert "match" in repository_entry(toy_grammar, name)


def test_a_token_the_grammar_does_not_reach_is_not_emitted(toy_grammar):
    # Strictly: `Parse` names what may appear, and it never names `LParen` —
    # the bracket is the span `Atom` opens.
    assert "lparen" not in toy_grammar["repository"]


def test_a_helper_production_is_inlined_rather_than_emitted(toy_grammar):
    # `Digit` is only ever part of `Number`; it is never tried on its own.
    assert "digit" not in toy_grammar["repository"]
    assert "[0-9]" in repository_entry(toy_grammar, "number")["match"]


# -- scopes -----------------------------------------------------------------


def test_a_style_becomes_the_scope_a_theme_knows_ending_in_the_language(toy_grammar):
    assert repository_entry(toy_grammar, "keyword")["name"] == "keyword.toy"
    assert repository_entry(toy_grammar, "comment")["name"] == "comment.toy"


def test_a_class_contributes_no_scope_of_its_own(toy_grammar):
    """`class(Literal) style(Float)` is a float to a theme and a literal to the
    phase that matches on it; only the style reaches the scope name."""
    assert (
        repository_entry(toy_grammar, "number")["name"] == "constant.numeric.float.toy"
    )


def test_a_style_reached_through_a_named_attribute_list(toy_grammar):
    assert repository_entry(toy_grammar, "ident")["name"] == "variable.other.toy"


def test_normal_is_no_scope_at_all(toy_grammar):
    # Unmatched text is already the editor's default colour, so `Normal` names
    # nothing rather than naming a style that means "unstyled".
    assert "name" not in repository_entry(toy_grammar, "space")


@pytest.mark.parametrize(
    "styles, scope",
    [
        (["Normal"], None),
        (["Keyword"], "keyword.toy"),
        (["Float", "Literal"], "constant.numeric.float.literal.toy"),
        (["Keyword", "Control"], "keyword.control.toy"),
        (["Mine"], "mine.toy"),
        (["Normal", "Punct"], "punct.toy"),
        ([], None),
    ],
)
def test_scope_derivation(styles, scope):
    assert scope_for(styles, "toy") == scope


# -- what the expressions actually match ------------------------------------


def test_a_keyword_does_not_match_inside_a_longer_word(toy_grammar):
    pattern = repository_entry(toy_grammar, "keyword")["match"]
    assert first_match_in(pattern, "if x") == "if"
    # Without the word boundaries TextMate would colour the `if` of `iffy`.
    assert first_match_in(pattern, "iffy") is None
    assert first_match_in(pattern, "let") == "let"


def test_a_length_based_choice_takes_the_longest_operator(toy_grammar):
    pattern = repository_entry(toy_grammar, "op")["match"]
    assert first_match_in(pattern, "<=") == "<="
    # `=` is an alternative of its own, so only the ordering keeps `==` whole.
    assert first_match_in(pattern, "==") == "=="
    assert first_match_in(pattern, "=") == "="
    assert first_match_in(pattern, "+") == "+"


def test_every_generated_expression_compiles_and_matches_its_token(toy_grammar):
    for name, expected in [
        ("space", "   "),
        ("comment", "# a note"),
        ("number", "12.5"),
        ("ident", "total_1"),
    ]:
        assert (
            first_match_in(repository_entry(toy_grammar, name)["match"], expected)
            == expected
        )


# -- the Parse target -------------------------------------------------------


def test_a_bracketing_production_becomes_a_span_that_nests(toy_grammar):
    atom = repository_entry(toy_grammar, "atom")
    assert (atom["begin"], atom["end"]) == ("\\(", "\\)")
    assert atom["name"] == "meta.atom.toy"
    # A span holds what its place in the grammar reaches, itself among them,
    # which is what makes the nesting recursive — the one thing a `match`
    # pattern could not have done.
    assert "atom" in included_entry_names(atom)


def test_the_brackets_themselves_are_scoped_as_punctuation(toy_grammar):
    atom = repository_entry(toy_grammar, "atom")
    assert atom["beginCaptures"]["0"]["name"] == "punctuation.section.atom.begin.toy"
    assert atom["endCaptures"]["0"]["name"] == "punctuation.section.atom.end.toy"


def test_a_non_bracketing_parse_production_contributes_nothing(toy_grammar):
    # `Expr` brackets nothing, so there is no span it could become.
    assert "expr" not in toy_grammar["repository"]


# -- a grammar of a single phase --------------------------------------------


def test_a_grammar_of_one_phase_starts_at_its_matches():
    grammar = grammar_of(ONE_PHASE)
    assert included_entry_names(grammar) == ["tokens"]
    assert "grammar" not in grammar["repository"]


def test_the_name_and_the_identifier_fall_back_to_the_grammar_file():
    grammar = grammar_of(ONE_PHASE, "my-toy.mgff")
    assert grammar["name"] == "MyToy"
    # An identifier is read by people and compared verbatim, so the words of the
    # name are kept apart rather than run together.
    assert grammar["scopeName"] == "source.my-toy"


# -- the extension around the grammar ---------------------------------------


@pytest.fixture(scope="module")
def extension_dir(tmp_path_factory) -> Path:
    out_dir = tmp_path_factory.mktemp("extension")
    TextMateGenerator().generate(
        model_of_text(fixture_text("textmate.mgff"), "textmate.mgff"), out_dir
    )
    return out_dir


def test_generate_writes_a_loadable_extension(extension_dir):
    assert (extension_dir / "syntaxes" / "Toy.tmLanguage.json").is_file()
    assert (extension_dir / "language-configuration.json").is_file()
    assert (extension_dir / "package.json").is_file()


def test_the_manifest_points_at_the_grammar_it_wrote(extension_dir):
    manifest = json.loads((extension_dir / "package.json").read_text(encoding="utf-8"))
    grammar = manifest["contributes"]["grammars"][0]
    assert grammar["path"] == "./syntaxes/Toy.tmLanguage.json"
    assert grammar["scopeName"] == "source.toy"
    assert (extension_dir / grammar["path"]).is_file()

    language = manifest["contributes"]["languages"][0]
    assert language["id"] == "toy"
    assert language["extensions"] == [".toy"]
    assert language["mimetypes"] == ["text/x-toy"]


def test_a_version_written_for_kate_is_padded_out_for_the_manifest():
    # `version(1)` is what the Kate backend wants; a manifest needs three parts.
    assert TextMateGenerator().package(model_of_text("> version(1)\n" + ONE_PHASE))[
        "version"
    ] == "1.0.0"


def test_the_configuration_folds_what_the_grammar_nests(extension_dir):
    configuration = json.loads(
        (extension_dir / "language-configuration.json").read_text(encoding="utf-8")
    )
    # VS Code folds and auto-closes by these pairs, not by anything in the
    # grammar, so the bracketing productions have to reach both files.
    assert configuration["brackets"] == [["(", ")"]]
    assert configuration["autoClosingPairs"] == [{"open": "(", "close": ")"}]


def test_comment_markers_come_from_the_file_attributes(extension_dir):
    configuration = json.loads(
        (extension_dir / "language-configuration.json").read_text(encoding="utf-8")
    )
    assert configuration["comments"] == {
        "lineComment": "#",
        "blockComment": ["#{", "#}"],
    }


def test_a_grammar_saying_nothing_about_comments_configures_none():
    generator = TextMateGenerator()
    model = model_of_text(ONE_PHASE)
    assert "comments" not in generator.language_configuration(
        model, generator.builder(model)
    )


# -- what the backend refuses ----------------------------------------------


def test_a_recursive_token_cannot_be_first_match_in():
    text = "t Parse (\n d Nested = \\( Nested \\)\n d File = ( Nested )*\n)"
    with pytest.raises(GeneratorError, match="reaches itself"):
        grammar_of(text)


def test_a_chain_not_ending_at_parse_is_reported():
    with pytest.raises(GeneratorError, match="it has to be 'Parse'"):
        grammar_of("t Other (\n d File = 0-9\n)")


def test_a_target_without_a_file_macro_is_reported():
    with pytest.raises(GeneratorError, match="no `File` macro"):
        grammar_of("t Parse (\n d Int = 0-9\n)")


def test_a_block_comment_needs_both_markers():
    generator = TextMateGenerator()
    model = model_of_text("> blockComment(/*)\n" + ONE_PHASE)
    with pytest.raises(GeneratorError, match="opening and the closing marker"):
        generator.language_configuration(model, generator.builder(model))


def test_a_token_matching_nothing_is_left_out_with_a_note(capsys):
    text = "t Parse (\n d Digit = 0-9\n d Maybe = ( Digit )*\n d File = ( Maybe )*\n)"
    grammar = grammar_of(text)
    assert included_entry_names(repository_entry(grammar, "tokens")) == []
    assert "can match the empty string" in capsys.readouterr().err


def test_a_target_off_the_chain_is_reported():
    """A phase nothing runs after and that runs after nothing never runs."""
    with pytest.raises(GeneratorError, match="all run first"):
        grammar_of(ONE_PHASE + "\nt Other (\n d Thing = a\n)")


def test_the_grammars_name_names_a_file_and_not_a_path(tmp_path):
    """A grammar names itself, and the manifest points at the file that was written."""
    text = (
        "> name(../../pwned)\n"
        "t Parse (\n"
        "    d File = ( A )*\n"
        "    d A = a\n"
        "      > style(Keyword)\n"
        ")\n"
    )
    out_dir = tmp_path / "out"
    backend = TextMateGenerator()
    grammar, _, manifest = backend.generate(
        backend_model := model_of_text(text), out_dir
    )
    assert grammar.parent == out_dir / "syntaxes"
    assert not list(tmp_path.parent.glob("pwned*"))

    manifest_json = json.loads(manifest.read_text(encoding="utf-8"))
    path = manifest_json["contributes"]["grammars"][0]["path"]
    assert (out_dir / path).resolve() == grammar.resolve()
    # The name itself is untouched: it is what the language is called.
    assert backend.language_name(backend_model) == "../../pwned"
