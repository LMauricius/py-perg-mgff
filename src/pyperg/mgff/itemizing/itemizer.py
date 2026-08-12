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

from ...diagnostics.errors import ItemizationError
from ...diagnostics.source import SourceFile
from ...diagnostics.span import Span
from .cst import Document, Group, Item, Line, Text
from .escapes import read_escape

WS = " \t"

#: How deeply groups may nest. A group is read by a recursive descent, and so is
#: every walk over the tree it builds, so the limit keeps a file no one wrote by
#: hand from exhausting the interpreter's stack. Nothing written to be read comes
#: near it.
MAX_GROUP_NESTING = 64


def itemize(source: SourceFile) -> Document:
    """Split a source file into lines, items and groups.

    Raises `LexError`, with a span, on anything the Part 1 grammar rejects.
    """
    return Itemizer(source).itemize_file()


def itemize_text(text: str, name: str = "<input>") -> Document:
    """Convenience wrapper for lexing a string."""
    return itemize(SourceFile(name, text))


class Itemizer:
    """A cursor over the source text, plus the recursive-descent routines."""

    def __init__(self, source: SourceFile) -> None:
        self.source = source
        self.text = source.text
        self.cursor = 0
        #: How many groups are open at the cursor.
        self.open_group_count = 0

    # -- cursor helpers ----------------------------------------------------

    def _at_end(self) -> bool:
        return self.cursor >= len(self.text)

    def _character_at_cursor(self) -> str:
        """The character under the cursor, or "" at end of input."""
        return self.text[self.cursor] if self.cursor < len(self.text) else ""

    def _span_from(self, start: int, end: int | None = None) -> Span:
        end = self.cursor if end is None else end
        return Span(
            self.source.position_at_offset(start), self.source.position_at_offset(end)
        )

    def _error(
        self, message: str, start: int, end: int | None = None
    ) -> ItemizationError:
        return ItemizationError(message, self._span_from(start, end))

    def _skip_spaces_and_tabs(self) -> None:
        while self._character_at_cursor() in WS and not self._at_end():
            self.cursor += 1

    def _skip_newline(self) -> bool:
        """Consume one NL (`\\r?\\n`) if present."""
        if (
            self._character_at_cursor() == "\r"
            and self.text[self.cursor + 1 : self.cursor + 2] == "\n"
        ):
            self.cursor += 2
            return True
        if self._character_at_cursor() == "\n":
            self.cursor += 1
            return True
        return False

    # -- grammar rules -----------------------------------------------------

    def itemize_file(self) -> Document:
        """`file = lines`, ending at end of input."""
        lines = self._read_lines(in_group=False)
        return Document(self.source.name, lines)

    def _read_lines(self, in_group: bool, open_at: int = 0) -> list[Line]:
        """`lines = line (NL line)*`.

        Stops at end of input at the top level, or at the closing `)` of the
        group opened at `open_at`. The `)` itself is left for the caller.
        """
        lines: list[Line] = []
        while True:
            lines.append(self._read_line())

            if self._character_at_cursor() == ")":
                if in_group:
                    return lines
                raise self._error("unmatched )", self.cursor, self.cursor + 1)

            if self._skip_newline():
                continue

            if self._at_end():
                if in_group:
                    raise self._error(
                        "unterminated group opened here", open_at, open_at + 1
                    )
                return lines

            # A line otherwise stops only at ")", NL or end of input, so what is
            # left here is a carriage return outside a `\r\n` pair.
            if self._character_at_cursor() == "\r":
                raise self._error(
                    "stray carriage return; a line ends with \\n or \\r\\n",
                    self.cursor,
                    self.cursor + 1,
                )
            raise self._error(
                f"unexpected character {self._character_at_cursor()!r}",
                self.cursor,
                self.cursor + 1,
            )

    def _read_line(self) -> Line:
        """`line = WS* (item (WS+ item)*)? WS*`, stopping before NL or `)`."""
        start = self.cursor
        items: list[Item] = []

        self._skip_spaces_and_tabs()
        while not self._at_end() and self._character_at_cursor() not in ")\r\n":
            items.append(self._read_item())
            # An item ends only at WS, NL, ")" or end of input, so the items of
            # a line are always separated by whitespace without checking here.
            self._skip_spaces_and_tabs()

        return Line(self._span_from(start), items)

    def _read_item(self) -> Item:
        """One item: text and groups in alternation, never two groups in a row."""
        start = self.cursor
        parts: list[Text | Group] = []
        previous_was_group = False

        while not self._at_end():
            char = self._character_at_cursor()

            if char == "(":
                if previous_was_group:
                    raise self._error(
                        "two groups in one item must be separated by text",
                        self.cursor,
                        self.cursor + 1,
                    )
                parts.append(self._read_group())
                previous_was_group = True
            elif char in WS or char in ")\r\n":
                break
            else:
                parts.append(self._read_text())
                previous_was_group = False

        return Item(self._span_from(start), parts)

    def _read_group(self) -> Group:
        """`group = "(" lines ")"`. The contents are lines of their own."""
        start = self.cursor
        if self.open_group_count >= MAX_GROUP_NESTING:
            raise self._error(
                f"groups nested more than {MAX_GROUP_NESTING} deep", start, start + 1
            )
        self.cursor += 1  # the "("
        self.open_group_count += 1
        lines = self._read_lines(in_group=True, open_at=start)
        self.open_group_count -= 1
        self.cursor += 1  # the ")"; _read_lines guarantees it is there
        return Group(self._span_from(start), lines)

    def _read_text(self) -> Text:
        """`text = (escape | literal)+`, with escapes resolved as they are read."""
        start = self.cursor
        chars: list[str] = []

        while not self._at_end():
            char = self._character_at_cursor()
            if char == "\\":
                try:
                    resolved, self.cursor = read_escape(self.text, self.cursor)
                except ItemizationError as err:
                    # The escape reader has no offsets; attach them here.
                    raise self._error(
                        err.message, start=self.cursor, end=self.cursor + 2
                    ) from None
                chars.append(resolved)
            elif char in WS or char in "()\r\n":
                break
            else:
                chars.append(char)
                self.cursor += 1

        return Text(self._span_from(start), "".join(chars))
