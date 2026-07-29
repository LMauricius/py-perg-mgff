"""Source positions and ranges, shared by every layer of the tool."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Position:
    """A single point in a source file. Offset is in characters, not bytes."""

    offset: int
    line: int  # 1-based
    column: int  # 1-based, in characters

    def __str__(self) -> str:
        return f"{self.line}:{self.column}"


@dataclass(frozen=True, slots=True)
class Span:
    """A half-open range `[start, end)` of a source file."""

    start: Position
    end: Position

    @staticmethod
    def between(start: Span, end: Span) -> Span:
        """The span covering both operands and everything in between."""
        return Span(start.start, end.end)

    def __str__(self) -> str:
        return f"{self.start}-{self.end}"
