"""Macro shapes and definitions: the order a call is read against."""

import re

import pytest

from pyperg.diagnostics.errors import SemanticError
from pyperg.mgff.grammar.macros import MacroDefinition, Scoped
from pyperg.mgff.grammar.signatures import NAME_CHARACTER, shape
from pyperg.mgff.lexing.cst import Item
from pyperg.mgff.lexing.lexer import lex_text
from pyperg.mgff.common.order import rule_tree_macros
from pyperg.mgff.semantics.context import CallContext
from pyperg.mgff.common.rules import MacroCall, Node, Reference, Repetition
from pyperg.mgff.semantics.model import resolve

def capture_args(item: Item, match: re.Match[str]) -> dict[str, object]:
    """What a capture carries: the name in front of the colon, and the rule.

    The item comes along because the node keeps it; a shape passes on whatever
    its definition is written to receive.
    """
    return {"item": item, "name": match["name"], "body": item.groups[0]}


def produce_capture(
    context: CallContext, item: Item, name: str, body: Node
) -> Node:
    """A stand-in for what a backend defines: a group carrying a name.

    The context goes unread, as it does for most macros: a capture means the
    same thing wherever it was written.
    """
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
    """The order a backend registering the capture reads items in."""
    return rule_tree_macros([CAPTURE])


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


SHADOWED = "d number:(R) = R R\nt Lex (\n d Digit = 0-9\n d Int = number:(Digit)\n)"


def test_a_registered_shape_outranks_a_definition_of_the_same_name():
    # `extra_macros` places a backend's shapes above every name, so the grammar
    # defining `number:(R)` does not take the shape away from the backend.
    assert isinstance(rule_of(SHADOWED, "Int"), MacroCall)


def test_a_shape_placed_after_the_names_yields_to_a_definition():
    # The order is what decides, and a caller assembling one by hand may still
    # put a shape below the point at which the grammar's own names are found.
    order = rule_tree_macros()
    scoped = next(index for index, macro in enumerate(order) if isinstance(macro, Scoped))
    below = order[: scoped + 1] + [CAPTURE] + order[scoped + 1 :]
    assert not isinstance(rule_of(SHADOWED, "Int", macros=below), MacroCall)
