"""Printing of diagnostics in the usual `file:line:col: message` form."""

from __future__ import annotations

import sys
from typing import TextIO

from .errors import PyPergError, SourceError
from .source import SourceFile


def format_error(error: PyPergError, source: SourceFile | None = None) -> str:
    """Render an error, with a source excerpt when both a span and a source exist."""
    if not isinstance(error, SourceError) or error.span is None:
        return f"error: {error}"

    where = source.name if source is not None else "<input>"
    head = f"{where}:{error.span.start}: error: {error.message}"
    if source is None:
        return head
    return f"{head}\n{source.excerpt(error.span)}"


def report(error: PyPergError, source: SourceFile | None = None, stream: TextIO | None = None) -> None:
    """Print an error to stderr (or `stream`)."""
    print(format_error(error, source), file=stream or sys.stderr)
