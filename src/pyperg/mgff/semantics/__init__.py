"""What a grammar means (Part 3): attributes, and the resolved model."""

from .attributes import collect_attributes, parse_attribute
from .context import CallContext
from .model import GrammarModel, Production, Target, resolve
from .nodes import Choice, MacroCall, Node, Reference, Repetition, Sequence

__all__ = [
    "CallContext",
    "Choice",
    "GrammarModel",
    "MacroCall",
    "Node",
    "Production",
    "Reference",
    "Repetition",
    "Sequence",
    "Target",
    "collect_attributes",
    "parse_attribute",
    "resolve",
]
