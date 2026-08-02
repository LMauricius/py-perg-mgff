"""The MGFF lexical layer (specification Part 1): text -> concrete syntax tree.

The grammar being implemented, written *about* MGFF rather than in it:

    file    = lines
    lines   = line (NL line)*
    line    = WS* (item (WS+ item)*)? WS*
    item    = text (group text)* group?
            | group (text group)* text?
    group   = "(" lines ")"
    text    = (escape | literal)+
    literal = CHAR except WS, "(", ")", "\\", "\\r", "\\n"

`(` and `)` are the only brackets; every other bracket character is ordinary
text. A group may span lines, so a line ends only at a newline that is outside
every group.
"""

from __future__ import annotations

from ...diagnostics.errors import LexError
from ...diagnostics.source import SourceFile
from ...diagnostics.span import Span
from .cst import File, Group, Item, Line, Text
from .escapes import read_escape

WS = " \t"


def lex(source: SourceFile) -> File:
    """Split a source file into lines, items and groups.

    Raises `LexError`, with a span, on anything the Part 1 grammar rejects.
    """
    return _Lexer(source).lex_file()


def lex_text(text: str, name: str = "<input>") -> File:
    """Convenience wrapper for lexing a string."""
    return lex(SourceFile(name, text))


class _Lexer:
    """A cursor over the source text, plus the recursive-descent routines."""

    def __init__(self, source: SourceFile) -> None:
        self.source = source
        self.text = source.text
        self.pos = 0

    # -- cursor helpers ----------------------------------------------------

    def _at_end(self) -> bool:
        return self.pos >= len(self.text)

    def _peek(self) -> str:
        """The character under the cursor, or "" at end of input."""
        return self.text[self.pos] if self.pos < len(self.text) else ""

    def _span(self, start: int, end: int | None = None) -> Span:
        end = self.pos if end is None else end
        return Span(self.source.position(start), self.source.position(end))

    def _error(self, message: str, start: int, end: int | None = None) -> LexError:
        return LexError(message, self._span(start, end))

    def _skip_ws(self) -> None:
        while self._peek() in WS and not self._at_end():
            self.pos += 1

    def _skip_newline(self) -> bool:
        """Consume one NL (`\\r?\\n`) if present."""
        if self._peek() == "\r" and self.text[self.pos + 1 : self.pos + 2] == "\n":
            self.pos += 2
            return True
        if self._peek() == "\n":
            self.pos += 1
            return True
        return False

    # -- grammar rules -----------------------------------------------------

    def lex_file(self) -> File:
        """`file = lines`, ending at end of input."""
        lines = self._lines(in_group=False)
        return File(self.source.name, lines)

    def _lines(self, in_group: bool, open_at: int = 0) -> list[Line]:
        """`lines = line (NL line)*`.

        Stops at end of input at the top level, or at the closing `)` of the
        group opened at `open_at`. The `)` itself is left for the caller.
        """
        lines: list[Line] = []
        while True:
            lines.append(self._line())

            if self._peek() == ")":
                if in_group:
                    return lines
                raise self._error("unmatched )", self.pos, self.pos + 1)

            if self._skip_newline():
                continue

            if self._at_end():
                if in_group:
                    raise self._error(
                        "unterminated group opened here", open_at, open_at + 1
                    )
                return lines

            # Unreachable: _line only stops at ")", NL or end of input.
            raise self._error(
                f"unexpected character {self._peek()!r}", self.pos, self.pos + 1
            )

    def _line(self) -> Line:
        """`line = WS* (item (WS+ item)*)? WS*`, stopping before NL or `)`."""
        start = self.pos
        items: list[Item] = []

        self._skip_ws()
        while not self._at_end() and self._peek() not in ")\r\n":
            items.append(self._item())
            # An item ends only at WS, NL, ")" or end of input, so the items of
            # a line are always separated by whitespace without checking here.
            self._skip_ws()

        return Line(self._span(start), items)

    def _item(self) -> Item:
        """One item: text and groups in alternation, never two groups in a row."""
        start = self.pos
        parts: list[Text | Group] = []
        previous_was_group = False

        while not self._at_end():
            char = self._peek()

            if char == "(":
                if previous_was_group:
                    raise self._error(
                        "two groups in one item must be separated by text",
                        self.pos,
                        self.pos + 1,
                    )
                parts.append(self._group())
                previous_was_group = True
            elif char in WS or char in ")\r\n":
                break
            else:
                parts.append(self._text())
                previous_was_group = False

        return Item(self._span(start), parts)

    def _group(self) -> Group:
        """`group = "(" lines ")"`. The contents are lines of their own."""
        start = self.pos
        self.pos += 1  # the "("
        lines = self._lines(in_group=True, open_at=start)
        self.pos += 1  # the ")"; _lines guarantees it is there
        return Group(self._span(start), lines)

    def _text(self) -> Text:
        """`text = (escape | literal)+`, with escapes resolved as they are read."""
        start = self.pos
        chars: list[str] = []

        while not self._at_end():
            char = self._peek()
            if char == "\\":
                try:
                    resolved, self.pos = read_escape(self.text, self.pos)
                except LexError as err:
                    # The escape reader has no offsets; attach them here.
                    raise self._error(
                        err.message, start=self.pos, end=self.pos + 2
                    ) from None
                chars.append(resolved)
            elif char in WS or char in "()\r\n":
                break
            else:
                chars.append(char)
                self.pos += 1

        return Text(self._span(start), "".join(chars))
