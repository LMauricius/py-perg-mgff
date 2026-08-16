"""The ANTLR backend."""

from pathlib import Path

import pytest

from pyperg.diagnostics.errors import GeneratorError
from pyperg.generators.antlr import AntlrGenerator
from pyperg.mgff.itemizing.itemizer import itemize_text
from pyperg.mgff.systems.grammar import parse, rule_tree_factory, resolveGrammar

def fixture_text(name: str) -> str:
    return (Path(__file__).parent / "fixtures" / name).read_text(encoding="utf-8")


def rendered_grammar_of(text: str, name: str = "<test>") -> str:
    """Resolve through the backend's own vocabulary, as `generate` does."""
    backend = AntlrGenerator()
    fileScope = parse(itemize_text(text, name), rule_tree_factory)
    return backend.render(resolveGrammar(fileScope, name, backend.macros()))


def two_phase(lexer: str, parser: str) -> str:
    """The smallest grammar with a lexer and a parser, around two bodies."""
    return f"t Lex (\n{lexer}\n)\n\nt Parse (\n> post(Lex)\n{parser}\n)\n"


def rule_body(grammar: str, name: str) -> str:
    """The one-line body of a rule, without its name or its semicolon."""
    for line in grammar.splitlines():
        stripped = line.strip()
        if stripped.startswith(f"{name} :") or stripped.startswith(f"fragment {name} :"):
            return stripped.split(" : ", 1)[1].rsplit(";", 1)[0].strip()
    raise AssertionError(f"no rule {name!r} in:\n{grammar}")


# -- the shape of a grammar the backend reads -------------------------------


def test_a_grammar_of_two_phases_becomes_a_lexer_and_a_parser():
    grammar = rendered_grammar_of(
        two_phase("d Int = ( 0-9 )+\n> token", "d Expr = Int")
    )
    assert grammar.startswith("grammar Test;")
    assert "INT : [0-9]+ ;" in grammar
    assert "expr : INT ;" in grammar


def test_a_grammar_of_one_phase_is_reported():
    with pytest.raises(GeneratorError, match="an ANTLR grammar has two phases"):
        rendered_grammar_of("t Parse (\nd Expr = a\n)")


def test_a_grammar_of_three_phases_is_reported():
    text = (
        "t Lex (\nd A = a\n> token\n)\n"
        "t Middle (\n> post(Lex)\nd B = A\n)\n"
        "t Parse (\n> post(Middle)\nd Expr = B\n)\n"
    )
    with pytest.raises(GeneratorError, match="and this grammar has 3"):
        rendered_grammar_of(text)


def test_the_grammar_is_named_by_its_own_attribute():
    grammar = rendered_grammar_of(
        "> name(Toy)\n" + two_phase("d Int = 0-9\n> token", "d Expr = Int")
    )
    assert grammar.startswith("grammar Toy;")


# -- tokens, fragments and channels -----------------------------------------


def test_a_lexer_production_carrying_token_is_a_token():
    grammar = rendered_grammar_of(
        two_phase("d Digit = 0-9\nd Int = ( Digit )+\n> token", "d Expr = Int")
    )
    assert "INT : DIGIT+ ;" in grammar
    assert "fragment DIGIT : [0-9] ;" in grammar


def test_a_lexer_production_pushed_to_the_read_list_is_a_token():
    text = (
        "t Lex (\nd Int = ( 0-9 )+\n> class(Int) push(tokens)\n)\n"
        "t Parse (\n> post(Lex) over(tokens)\nd Expr = Int\n)\n"
    )
    grammar = rendered_grammar_of(text)
    assert "INT : [0-9]+ ;" in grammar
    assert "fragment" not in grammar


def test_a_grammar_whose_lexer_produces_no_token_is_reported():
    with pytest.raises(GeneratorError, match="is a token, so the parser would have"):
        rendered_grammar_of(two_phase("d Int = ( 0-9 )+", "d Expr = a"))


def test_the_parser_may_not_call_a_fragment():
    with pytest.raises(GeneratorError, match="which is a fragment and produces no token"):
        rendered_grammar_of(
            two_phase("d Digit = 0-9\nd Int = ( Digit )+\n> token", "d Expr = Digit")
        )


def test_skip_becomes_a_lexer_command():
    grammar = rendered_grammar_of(
        two_phase("d Space = ( \\_|\\t )+\n> token skip\nd Int = 0-9\n> token", "d Expr = Int")
    )
    assert "SPACE : [ \\t]+ -> skip ;" in grammar


def test_skip_false_opts_out_of_skipping():
    grammar = rendered_grammar_of(
        two_phase("d Int = 0-9\n> token skip(false)", "d Expr = Int")
    )
    assert "-> skip" not in grammar


def test_a_second_pushed_list_becomes_a_channel():
    grammar = rendered_grammar_of(fixture_text("antlr.mgff"), "antlr.mgff")
    # A combined grammar declares no channel of its own, so the one list kept
    # out of the parser's way goes to the predefined `HIDDEN`.
    assert "channels" not in grammar
    assert "-> channel(HIDDEN)" in grammar


def test_two_different_channels_are_reported():
    text = (
        "t Lex (\nd Int = 0-9\n> class(Int) push(tokens) push(a)\n"
        "d Space = \\_\n> class(Space) push(tokens) push(b)\n)\n"
        "t Parse (\n> post(Lex) over(tokens)\nd Expr = Int\n/ Space\n)\n"
    )
    with pytest.raises(GeneratorError, match="one grammar file has one channel"):
        rendered_grammar_of(text)


def test_pushing_to_two_lists_besides_the_read_one_is_reported():
    text = (
        "t Lex (\nd Int = 0-9\n> class(Int) push(tokens) push(a) push(b)\n)\n"
        "t Parse (\n> post(Lex) over(tokens)\nd Expr = Int\n)\n"
    )
    with pytest.raises(GeneratorError, match="an ANTLR token reaches one channel"):
        rendered_grammar_of(text)


def test_a_skipped_match_may_not_also_reach_a_channel():
    text = (
        "t Lex (\nd Space = \\_\n> class(Space) push(tokens) push(hidden) skip\n)\n"
        "t Parse (\n> post(Lex) over(tokens)\nd Expr = Space\n)\n"
    )
    with pytest.raises(GeneratorError, match="both skipped and pushed"):
        rendered_grammar_of(text)


# -- matching characters ----------------------------------------------------


def test_a_character_set_becomes_a_lexer_set():
    grammar = rendered_grammar_of(
        two_phase("d Word = ( a-z|A-Z|_|Decimal_Number )+\n> token", "d Expr = Word")
    )
    assert rule_body(grammar, "WORD") == "[a-zA-Z_\\p{Nd}]+"


def test_a_run_of_single_characters_becomes_one_literal():
    grammar = rendered_grammar_of(two_phase("d Op = < =\n> token", "d Expr = Op"))
    assert rule_body(grammar, "OP") == "'<='"


def test_a_character_needing_an_escape_is_escaped():
    grammar = rendered_grammar_of(
        two_phase("d Quote = \\x27 \\n\n> token", "d Expr = Quote")
    )
    assert rule_body(grammar, "QUOTE") == "'\\'\\n'"


def test_the_parser_may_not_hold_a_character_set():
    with pytest.raises(GeneratorError, match="the parser reads tokens, so the set"):
        rendered_grammar_of(
            two_phase("d Int = 0-9\n> token", "d Expr = Int\nd Bad = a-z")
        )


def test_a_single_character_in_the_parser_is_an_inline_literal():
    grammar = rendered_grammar_of(
        two_phase("d Int = 0-9\n> token", "d Expr = \\( Int \\)")
    )
    assert rule_body(grammar, "expr") == "'(' INT ')'"


# -- choice, and the longest match ------------------------------------------


def test_an_order_based_choice_keeps_its_written_order():
    grammar = rendered_grammar_of(
        two_phase("d Int = 0-9\n> token", "d Expr = (Int)/(Int Int)")
    )
    assert rule_body(grammar, "expr") == "( INT | INT INT )"


def test_a_length_based_choice_puts_the_longest_fixed_option_first():
    grammar = rendered_grammar_of(
        two_phase("d Int = 0-9\n> token", "d Expr = (\\()|(\\( \\))")
    )
    assert rule_body(grammar, "expr") == "( '()' | '(' )"


# -- where a match goes -----------------------------------------------------


def test_store_becomes_a_label_at_every_call():
    grammar = rendered_grammar_of(
        two_phase(
            "d Int = 0-9\n> token",
            "d Argument = Int\n> store(value)\nd Expr = Argument",
        )
    )
    assert rule_body(grammar, "expr") == "value=argument"


def test_a_label_a_loop_repeats_becomes_a_list_throughout():
    grammar = rendered_grammar_of(
        two_phase(
            "d Int = 0-9\n> token",
            "d Argument = Int\n> store(value)\nd Expr = Argument ( , Argument )*",
        )
    )
    assert rule_body(grammar, "expr") == "value+=argument ( ',' value+=argument )*"


def test_push_becomes_a_list_label():
    grammar = rendered_grammar_of(
        two_phase(
            "d Int = 0-9\n> token",
            "d Argument = Int\n> push(values)\nd Expr = ( Argument )+",
        )
    )
    assert rule_body(grammar, "expr") == "values+=argument+"


# -- left recursion ---------------------------------------------------------


def test_direct_left_recursion_is_kept_as_written():
    grammar = rendered_grammar_of(
        two_phase("d Int = 0-9\n> token\nd Plus = +\n> token", "d Expr = Expr Plus Expr\n/ Int")
    )
    assert "  : expr PLUS expr" in grammar
    assert "  | INT" in grammar


def test_indirect_left_recursion_is_rewritten_as_a_repetition():
    grammar = rendered_grammar_of(
        two_phase(
            "d Int = 0-9\n> token\nd Plus = +\n> token\nd Star = *\n> token",
            "d Expr = Term Plus Expr\n/ Term\nd Term = Expr Star Term\n/ Int",
        )
    )
    # The cycle is gone: `expr` no longer begins with `term`, so neither rule
    # can reach itself without consuming a token first.
    assert rule_body(grammar, "expr") == (
        "( INT PLUS expr | INT ) ( STAR term PLUS expr | STAR term )*"
    )
    assert "  : expr STAR term" in grammar


def test_a_rule_whose_every_alternative_recurses_is_reported():
    with pytest.raises(GeneratorError, match="every alternative recurses"):
        rendered_grammar_of(
            two_phase("d Int = 0-9\n> token\nd Plus = +\n> token", "d Expr = Expr Plus Expr")
        )


def test_left_recursion_reached_through_a_group_is_reported():
    text = two_phase(
        "d Int = 0-9\n> token\nd Plus = +\n> token",
        "d Expr = ( Expr Plus )? Int",
    )
    with pytest.raises(GeneratorError, match="reached through a group"):
        rendered_grammar_of(text)


# -- the file it writes -----------------------------------------------------


def test_the_grammar_is_written_as_one_file(tmp_path):
    backend = AntlrGenerator()
    fileScope = parse(
        itemize_text(fixture_text("antlr.mgff"), "antlr.mgff"), rule_tree_factory
    )
    model = resolveGrammar(fileScope, "antlr.mgff", backend.macros())
    written_paths = backend.generate(model, tmp_path)
    assert [path.name for path in written_paths] == ["Toy.g4"]
    assert written_paths[0].read_text(encoding="utf-8") == backend.render(model)


def test_the_start_production_is_written_first():
    grammar = rendered_grammar_of(
        two_phase("d Int = 0-9\n> token", "d Expr = Int\nd File = ( Expr )*")
    )
    rules = [line.split()[0] for line in grammar.splitlines() if " : " in line]
    assert rules.index("file") < rules.index("expr")
