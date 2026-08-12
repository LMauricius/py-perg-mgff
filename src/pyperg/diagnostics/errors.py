"""The error hierarchy. Every user-facing failure is a `PyPergError`."""

from __future__ import annotations

from .span import Span


class PyPergError(Exception):
    """Base of every error the tool reports to the user."""


class SourceError(PyPergError):
    """An error attributable to a place in a source file."""

    def __init__(self, message: str, span: Span | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.span = span


class ItemizationError(SourceError):
    """Part 1: the file does not split into lines, items and groups."""


class GrammarSyntaxError(SourceError):
    """Part 2: the pieces are well-formed but their arrangement has no role.

    Named with a `Grammar` prefix to leave the built-in `SyntaxError` alone.
    """


class SemanticError(SourceError):
    """Part 2/3: names, arities or shapes do not resolve."""


class GeneratorError(PyPergError):
    """A backend could not produce output."""
