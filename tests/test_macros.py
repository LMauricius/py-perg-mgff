"""Macro shapes and definitions: the order a call is read against."""

import re

import pytest

from pyperg.diagnostics.errors import SemanticError
from pyperg.mgff.semantics.macros import MacroDefinition, ScopeLookupPoint
from pyperg.mgff.semantics.signatures import NAME_CHARACTER, make_shape
from pyperg.mgff.itemizing.cst import Item
from pyperg.mgff.itemizing.itemizer import itemize_text
from pyperg.mgff.common.order import rule_tree_macro_order
from pyperg.mgff.systems.context import CallContext
from pyperg.mgff.common.rules import MacroCall, Rule, Reference, Repetition
from pyperg.mgff.systems.grammar import parse, rule_tree_factory, resolveGrammar

def capture_args(item: Item, match: re.Match[str]) -> dict[str, object]:
    """What a capture carries: the name in front of the colon, and the rule.

    The item comes along because the node keeps it; a shape passes on whatever
    its definition is written to receive.
    """
    return {"item": item, "name": match["name"], "body": item.groups[0]}


def produce_capture(
    context: CallContext, item: Item, name: str, body: Rule
) -> Rule:
    """A stand-in for what a backend defines: a group carrying a name.

    The context goes unread, as it does for most macros: a capture means the
    same thing wherever it was written.
    """
    return MacroCall(macro=CAPTURE, item=item, arguments=[body])


#: `name:(rule)`, and `:(rule)` for one with no name.
CAPTURE = MacroDefinition(
    shape=make_shape("capture", rf"(?P<name>{NAME_CHARACTER}*):\(\)", capture_args),
    produce_call=produce_capture,
)

GRAMMAR = """
t Lex (
    d Digit = 0-9
    d Int = number:( ( Digit )+ )
    d Any = :( Digit )
)
"""


def macro_order_with_capture() -> list:
    """The order a backend registering the capture reads items in."""
    return rule_tree_macro_order([CAPTURE])


def model_from_text(text: str, macros: list | None = None):
    fileScope = parse(itemize_text(text, "<test>"), rule_tree_factory)
    return resolveGrammar(fileScope, "<test>", macros or macro_order_with_capture())


def lex_target_rule_of(text: str, name: str, macros: list | None = None):
    return model_from_text(text, macros).target("Lex").productions[name].rule


# -- a definition a backend adds --------------------------------------------


def test_a_backends_definition_claims_the_shape_it_matches():
    rule = lex_target_rule_of(GRAMMAR, "Int")
    assert isinstance(rule, MacroCall) and rule.macro is CAPTURE


def test_a_definition_is_called_with_what_its_shape_extracted():
    # `name` comes from the shape's pattern, `body` from the item's group.
    assert lex_target_rule_of(GRAMMAR, "Int").item.text == "number:"
    assert lex_target_rule_of(GRAMMAR, "Any").item.text == ":"


def test_a_group_reaches_the_definition_already_read_as_a_rule():
    argument = lex_target_rule_of(GRAMMAR, "Int").arguments[0]
    assert isinstance(argument, Repetition)
    assert argument.body == Reference("Digit")


def test_a_shape_no_macro_answers_to_is_an_unknown_name():
    # The very same grammar, read without the backend that gives it meaning.
    with pytest.raises(SemanticError, match="unknown name"):
        model_from_text(GRAMMAR, macros=rule_tree_macro_order())


# -- the order ---------------------------------------------------------------


SHADOWED = "d number:(R) = R R\nt Lex (\n d Digit = 0-9\n d Int = number:(Digit)\n)"


def test_a_registered_shape_outranks_a_definition_of_the_same_name():
    # `extra_macros` places a backend's shapes above every name, so the grammar
    # defining `number:(R)` does not take the shape away from the backend.
    assert isinstance(lex_target_rule_of(SHADOWED, "Int"), MacroCall)


def test_a_shape_placed_after_the_names_yields_to_a_definition():
    # The order is what decides, and a caller assembling one by hand may still
    # put a shape below the point at which the grammar's own names are found.
    order = rule_tree_macro_order()
    scope_lookup_index = next(
        index
        for index, macro in enumerate(order)
        if isinstance(macro, ScopeLookupPoint)
    )
    order_with_capture_below_names = (
        order[: scope_lookup_index + 1] + [CAPTURE] + order[scope_lookup_index + 1 :]
    )
    assert not isinstance(
        lex_target_rule_of(SHADOWED, "Int", macros=order_with_capture_below_names),
        MacroCall,
    )
