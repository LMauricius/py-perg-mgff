"""Macro shapes and definitions: the order a call is read against."""

import re

import pytest

from pyperg.diagnostics.errors import SemanticError
from pyperg.grammar.macros import MacroDefinition, Scoped
from pyperg.grammar.shapes import NAME_CHARACTER, shape
from pyperg.mgff.cst import Item
from pyperg.mgff.lexer import lex_text
from pyperg.semantics.builtins import rule_tree_macros
from pyperg.semantics.model import MacroCall, Node, Reference, Repetition, resolve


def capture_args(item: Item, match: re.Match[str]) -> dict[str, object]:
    """What a capture carries: the name in front of the colon, and the rule.

    The item comes along because the node keeps it; a shape passes on whatever
    its definition is written to receive.
    """
    return {"item": item, "name": match["name"], "body": item.groups[0]}


def produce_capture(item: Item, name: str, body: Node) -> Node:
    """A stand-in for what a backend defines: a group carrying a name."""
    return MacroCall(macro=CAPTURE, item=item, arguments=[body])


#: `name:(rule)`, and `:(rule)` for one with no name.
CAPTURE = MacroDefinition(
    shape=shape("capture", rf"(?P<name>{NAME_CHARACTER}*):\(\)", capture_args),
    produce_call=produce_capture,
)

GRAMMAR = """
t Lex (
    d Digit = 0-9
    d Int = number:( ( Digit )+ )
    d Any = :( Digit )
)
"""


def with_capture() -> list:
    """The default order, with the capture where it yields to a definition.

    A capture carries groups, so it is placed after the point at which the
    grammar's own definitions carrying arguments are consulted. That is what
    makes a grammar defining `number:(R)` win over it.
    """
    order = rule_tree_macros()
    scoped = next(index for index, macro in enumerate(order) if isinstance(macro, Scoped))
    return order[: scoped + 1] + [CAPTURE] + order[scoped + 1 :]


def model_of(text: str, macros: list | None = None):
    return resolve(lex_text(text, "<test>"), "<test>", macros or with_capture())


def rule_of(text: str, name: str, macros: list | None = None):
    return model_of(text, macros).target("Lex").productions[name].rule


# -- a definition a backend adds --------------------------------------------


def test_a_backends_definition_claims_the_shape_it_matches():
    rule = rule_of(GRAMMAR, "Int")
    assert isinstance(rule, MacroCall) and rule.macro is CAPTURE


def test_a_definition_is_called_with_what_its_shape_extracted():
    # `name` comes from the shape's pattern, `body` from the item's group.
    assert rule_of(GRAMMAR, "Int").item.text == "number:"
    assert rule_of(GRAMMAR, "Any").item.text == ":"


def test_a_group_reaches_the_definition_already_read_as_a_rule():
    argument = rule_of(GRAMMAR, "Int").arguments[0]
    assert isinstance(argument, Repetition)
    assert argument.body == Reference("Digit")


def test_a_shape_no_macro_answers_to_is_an_unknown_name():
    # The very same grammar, read without the backend that gives it meaning.
    with pytest.raises(SemanticError, match="unknown name"):
        model_of(GRAMMAR, macros=rule_tree_macros())


# -- the order ---------------------------------------------------------------


def test_a_definition_outranks_a_shape_placed_after_it():
    text = "d number:(R) = R R\nt Lex (\n d Digit = 0-9\n d Int = number:(Digit)\n)"
    # `number:(…)` is defined, so the grammar's definition is found first.
    assert not isinstance(rule_of(text, "Int"), MacroCall)


def test_a_shape_placed_first_hides_a_definition_of_the_same_name():
    text = "t Lex (\n d Digit = 0-9\n d Int = number:(Digit)\n)"
    first = [CAPTURE] + rule_tree_macros()
    assert isinstance(rule_of(text, "Int", macros=first), MacroCall)
