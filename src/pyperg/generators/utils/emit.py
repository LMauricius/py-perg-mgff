"""An indent-aware line writer.

Every backend writes nested text, so every backend would otherwise carry its own
indentation counter.
"""

from __future__ import annotations

from contextlib import contextmanager
from collections.abc import Iterator


class Emitter:
    """Collects lines of output, tracking how deep they sit."""

    def __init__(self, indent: str = "  ") -> None:
        self.indent = indent
        self.depth = 0
        self.lines: list[str] = []

    def write_line(self, text: str = "") -> None:
        """Write one line at the current depth; an empty line stays empty."""
        self.lines.append(f"{self.indent * self.depth}{text}" if text else "")

    @contextmanager
    def indented(self) -> Iterator[None]:
        """Write the lines of the block one level deeper."""
        self.depth += 1
        try:
            yield
        finally:
            self.depth -= 1

    def render(self) -> str:
        """Everything written so far, as one string ending in a newline."""
        return "\n".join(self.lines) + "\n"
