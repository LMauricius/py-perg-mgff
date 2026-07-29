"""Source text with the bookkeeping needed to turn offsets into positions."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .span import Position, Span


@dataclass
class SourceFile:
    """A loaded source file: its text, its origin, and its line offsets.

    `name` is what diagnostics print; it need not be a real path, so text held in
    memory can be reported on just like a file.
    """

    name: str
    text: str
    # Offset of the first character of each line, in order. Always starts with 0.
    line_starts: list[int] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        starts = [0]
        for i, ch in enumerate(self.text):
            if ch == "\n":
                starts.append(i + 1)
        self.line_starts = starts

    @staticmethod
    def read(path: str | Path) -> SourceFile:
        """Load a file as UTF-8."""
        path = Path(path)
        return SourceFile(str(path), path.read_text(encoding="utf-8"))

    def position(self, offset: int) -> Position:
        """The line/column of an offset. Both are 1-based."""
        # Binary search for the last line start at or before `offset`.
        lo, hi = 0, len(self.line_starts) - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if self.line_starts[mid] <= offset:
                lo = mid
            else:
                hi = mid - 1
        return Position(offset, lo + 1, offset - self.line_starts[lo] + 1)

    def line_text(self, line: int) -> str:
        """The text of a 1-based line number, without its terminator."""
        if not 1 <= line <= len(self.line_starts):
            return ""
        start = self.line_starts[line - 1]
        end = self.line_starts[line] if line < len(self.line_starts) else len(self.text)
        return self.text[start:end].rstrip("\r\n")

    def excerpt(self, span: Span) -> str:
        """The source line of `span.start` with a caret run under the span."""
        line = self.line_text(span.start.line)
        width = 1
        if span.end.line == span.start.line:
            width = max(1, span.end.column - span.start.column)
        return f"{line}\n{' ' * (span.start.column - 1)}{'^' * width}"
