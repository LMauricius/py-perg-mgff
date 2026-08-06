"""The TextMate backend."""

import json
from pathlib import Path

import pytest

from pyperg.diagnostics.errors import GeneratorError
from pyperg.generators.textmate import TextMateGenerator
from pyperg.generators.textmate.scopes import scope_for
from pyperg.mgff.lexing.lexer import lex_text
from pyperg.mgff.semantics.model import resolve

regex = pytest.importorskip("regex", reason="the generated patterns use \\p{…}")


def read_fixture(name: str) -> str:
    return (Path(__file__).parent / "fixtures" / name).read_text(encoding="utf-8")


def _model(text: str, name: str = "<test>"):
    """Resolve through the backend's own vocabulary, as `generate` does."""
    return resolve(lex_text(text, name), name, TextMateGenerator().macros())


def grammar_of(text: str, name: str = "<test>") -> dict:
    return json.loads(TextMateGenerator().render(_model(text, name)))


def entry(grammar: dict, name: str) -> dict:
    found = grammar["repository"].get(name)
    assert found is not None, f"no repository entry named {name}"
    return found


def included(pattern: dict) -> list[str]:
    """The entry names one `patterns` list refers to, in order."""
    return [one["include"].lstrip("#") for one in pattern["patterns"] if "include" in one]


def matched(pattern: str, text: str) -> str | None:
    """What the pattern finds in the text, as VS Code's engine would search for it."""
    found = regex.search(pattern, text)
    return found.group(0) if found else None


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
def toy() -> dict:
    return grammar_of(read_fixture("textmate.mgff"), "textmate.mgff")


def test_the_grammar_names_itself_and_its_scope(toy):
    assert toy["name"] == "Toy"
    assert toy["scopeName"] == "source.toy"
    assert toy["fileTypes"] == ["toy"]


def test_a_document_starts_at_the_grammar_entry(toy):
    assert included(toy) == ["grammar"]


def test_the_grammar_entry_tries_brackets_before_tokens(toy):
    # `(` must open its own span rather than being eaten by a token of the same
    # shape, and the tokens follow in the order `Lex` names them.
    included_here = included(entry(toy, "grammar"))
    assert included_here[0] == "atom"
    assert set(included_here[1:]) == {"comment", "keyword", "number", "ident", "space", "op"}


def test_every_token_a_context_reaches_becomes_an_entry_of_its_own(toy):
    # One entry per token, included where it is reachable, rather than the same
    # expression written out in every context that can reach it.
    for name in ("space", "comment", "keyword", "number", "ident", "op"):
        assert "match" in entry(toy, name)


def test_a_token_the_grammar_does_not_reach_is_not_emitted(toy):
    # Strictly: `Parse` names what may appear, and it never names `LParen` —
    # the bracket is the span `Atom` opens.
    assert "lparen" not in toy["repository"]


def test_a_helper_production_is_inlined_rather_than_emitted(toy):
    # `Digit` is only ever part of `Number`; it is never tried on its own.
    assert "digit" not in toy["repository"]
    assert "[0-9]" in entry(toy, "number")["match"]


# -- scopes -----------------------------------------------------------------


def test_a_class_becomes_the_scope_a_theme_knows_ending_in_the_language(toy):
    assert entry(toy, "keyword")["name"] == "keyword.toy"
    assert entry(toy, "comment")["name"] == "comment.toy"


def test_extra_classes_survive_after_the_one_that_colours_the_token(toy):
    assert entry(toy, "number")["name"] == "constant.numeric.float.literal.toy"


def test_autoclass_reaches_a_scope_through_the_shared_synonyms(toy):
    assert entry(toy, "ident")["name"] == "variable.other.toy"


def test_normal_is_no_scope_at_all(toy):
    # Unmatched text is already the editor's default colour, so `Normal` names
    # nothing rather than naming a style that means "unstyled".
    assert "name" not in entry(toy, "space")


@pytest.mark.parametrize(
    "classes, scope",
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
def test_scope_derivation(classes, scope):
    assert scope_for(classes, "toy") == scope


# -- what the expressions actually match ------------------------------------


def test_a_keyword_does_not_match_inside_a_longer_word(toy):
    pattern = entry(toy, "keyword")["match"]
    assert matched(pattern, "if x") == "if"
    # Without the word boundaries TextMate would colour the `if` of `iffy`.
    assert matched(pattern, "iffy") is None
    assert matched(pattern, "let") == "let"


def test_a_length_based_choice_takes_the_longest_operator(toy):
    pattern = entry(toy, "op")["match"]
    assert matched(pattern, "<=") == "<="
    # `=` is an alternative of its own, so only the ordering keeps `==` whole.
    assert matched(pattern, "==") == "=="
    assert matched(pattern, "=") == "="
    assert matched(pattern, "+") == "+"


def test_every_generated_expression_compiles_and_matches_its_token(toy):
    for name, expected in [
        ("space", "   "),
        ("comment", "# a note"),
        ("number", "12.5"),
        ("ident", "total_1"),
    ]:
        assert matched(entry(toy, name)["match"], expected) == expected


# -- the Parse target -------------------------------------------------------


def test_a_bracketing_production_becomes_a_span_that_nests(toy):
    atom = entry(toy, "atom")
    assert (atom["begin"], atom["end"]) == ("\\(", "\\)")
    assert atom["name"] == "meta.atom.toy"
    # A span holds what its place in the grammar reaches, itself among them,
    # which is what makes the nesting recursive — the one thing a `match`
    # pattern could not have done.
    assert "atom" in included(atom)


def test_the_brackets_themselves_are_scoped_as_punctuation(toy):
    atom = entry(toy, "atom")
    assert atom["beginCaptures"]["0"]["name"] == "punctuation.section.atom.begin.toy"
    assert atom["endCaptures"]["0"]["name"] == "punctuation.section.atom.end.toy"


def test_a_non_bracketing_parse_production_contributes_nothing(toy):
    # `Expr` brackets nothing, so there is no span it could become.
    assert "expr" not in toy["repository"]


# -- a grammar with only a Lex target ---------------------------------------


def test_a_lex_only_grammar_starts_at_its_tokens():
    grammar = grammar_of(LEX_ONLY)
    assert included(grammar) == ["tokens"]
    assert "grammar" not in grammar["repository"]


def test_the_name_and_the_identifier_fall_back_to_the_grammar_file():
    grammar = grammar_of(LEX_ONLY, "my-toy.mgff")
    assert grammar["name"] == "MyToy"
    # An identifier is read by people and compared verbatim, so the words of the
    # name are kept apart rather than run together.
    assert grammar["scopeName"] == "source.my-toy"


# -- the extension around the grammar ---------------------------------------


@pytest.fixture(scope="module")
def written(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("extension")
    TextMateGenerator().generate(_model(read_fixture("textmate.mgff"), "textmate.mgff"), out)
    return out


def test_generate_writes_a_loadable_extension(written):
    assert (written / "syntaxes" / "Toy.tmLanguage.json").is_file()
    assert (written / "language-configuration.json").is_file()
    assert (written / "package.json").is_file()


def test_the_manifest_points_at_the_grammar_it_wrote(written):
    manifest = json.loads((written / "package.json").read_text(encoding="utf-8"))
    grammar = manifest["contributes"]["grammars"][0]
    assert grammar["path"] == "./syntaxes/Toy.tmLanguage.json"
    assert grammar["scopeName"] == "source.toy"
    assert (written / grammar["path"]).is_file()

    language = manifest["contributes"]["languages"][0]
    assert language["id"] == "toy"
    assert language["extensions"] == [".toy"]
    assert language["mimetypes"] == ["text/x-toy"]


def test_a_version_written_for_kate_is_padded_out_for_the_manifest():
    # `version(1)` is what the Kate backend wants; a manifest needs three parts.
    assert TextMateGenerator().package(_model("> version(1)\n" + LEX_ONLY))[
        "version"
    ] == "1.0.0"


def test_the_configuration_folds_what_the_grammar_nests(written):
    configuration = json.loads(
        (written / "language-configuration.json").read_text(encoding="utf-8")
    )
    # VS Code folds and auto-closes by these pairs, not by anything in the
    # grammar, so the bracketing productions have to reach both files.
    assert configuration["brackets"] == [["(", ")"]]
    assert configuration["autoClosingPairs"] == [{"open": "(", "close": ")"}]


def test_comment_markers_come_from_the_file_attributes(written):
    configuration = json.loads(
        (written / "language-configuration.json").read_text(encoding="utf-8")
    )
    assert configuration["comments"] == {
        "lineComment": "#",
        "blockComment": ["#{", "#}"],
    }


def test_a_grammar_saying_nothing_about_comments_configures_none():
    generator = TextMateGenerator()
    model = _model(LEX_ONLY)
    assert "comments" not in generator.language_configuration(model, generator.builder(model))


# -- what the backend refuses ----------------------------------------------


def test_a_recursive_token_cannot_be_matched():
    text = "t Lex (\n d Nested = \\( Nested \\)\n d File = ( Nested )*\n)"
    with pytest.raises(GeneratorError, match="reaches itself"):
        grammar_of(text)


def test_a_grammar_with_neither_target_is_reported():
    with pytest.raises(GeneratorError, match="no `Lex` or `Parse` target"):
        grammar_of("t Other (\n d File = 0-9\n)")


def test_a_target_without_a_file_macro_is_reported():
    with pytest.raises(GeneratorError, match="no `File` macro"):
        grammar_of("t Lex (\n d Int = 0-9\n)")


def test_a_block_comment_needs_both_markers():
    generator = TextMateGenerator()
    model = _model("> blockComment(/*)\n" + LEX_ONLY)
    with pytest.raises(GeneratorError, match="opening and the closing marker"):
        generator.language_configuration(model, generator.builder(model))


def test_a_token_matching_nothing_is_left_out_with_a_note(capsys):
    text = "t Lex (\n d Digit = 0-9\n d Maybe = ( Digit )*\n d File = ( Maybe )*\n)"
    grammar = grammar_of(text)
    assert included(entry(grammar, "tokens")) == []
    assert "can match the empty string" in capsys.readouterr().err


def test_an_ignored_target_is_reported_on_stderr(capsys):
    grammar_of(LEX_ONLY + "\nt Other (\n d Thing = a\n)")
    assert "is not generated" in capsys.readouterr().err
