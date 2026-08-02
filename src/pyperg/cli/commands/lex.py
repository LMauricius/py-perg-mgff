"""`pyperg lex`: show the lexical structure of a grammar file (Part 1)."""

from __future__ import annotations

import argparse

from ...diagnostics.source import SourceFile
from ...mgff.lexing.cst import File, Group, Item, Line, Text, render_item
from ...mgff.lexing.lexer import lex
from .base import Command

class LexCommand(Command):
    name = "lex"
    help = "show how a file splits into lines, items and groups"

    def add_cli_arguments(self, cli_parser: argparse.ArgumentParser) -> None:
        cli_parser.add_argument("file", help="the MGFF file to read")
        cli_parser.add_argument(
            "--spans",
            action="store_true",
            help="annotate every node with its source span",
        )
        cli_parser.add_argument(
            "--blank-lines",
            action="store_true",
            help="show blank lines instead of skipping them",
        )

    def run(self, cli_args: argparse.Namespace) -> int:
        source = SourceFile.read(cli_args.file)
        tree = lex(source)
        print(
            _render_file(tree, spans=cli_args.spans, blanks=cli_args.blank_lines),
            end="",
        )
        return 0


# -- rendering -------------------------------------------------------------


def _render_file(file: File, spans: bool, blanks: bool) -> str:
    out: list[str] = [f"file {file.name}\n"]
    _render_lines(file.lines, depth=1, out=out, spans=spans, blanks=blanks)
    return "".join(out)


def _render_lines(lines: list[Line], depth: int, out: list[str], spans: bool, blanks: bool) -> None:
    for line in lines:
        if line.is_blank and not blanks:
            continue
        _write(out, depth, "line", f"({len(line.items)} items)", line.span if spans else None)
        for item in line.items:
            _render_item(item, depth + 1, out, spans, blanks)


def _render_item(item: Item, depth: int, out: list[str], spans: bool, blanks: bool) -> None:
    _write(out, depth, "item", _abbreviate(render_item(item)), item.span if spans else None)
    for part in item.parts:
        if isinstance(part, Text):
            _write(out, depth + 1, "text", repr(part.value), part.span if spans else None)
        else:
            _render_group(part, depth + 1, out, spans, blanks)


def _render_group(group: Group, depth: int, out: list[str], spans: bool, blanks: bool) -> None:
    _write(out, depth, "group", f"({len(group.lines)} lines)", group.span if spans else None)
    _render_lines(group.lines, depth + 1, out, spans, blanks)


def _abbreviate(text: str, limit: int = 60) -> str:
    """Shorten the one-line summary of an item; its parts follow underneath anyway."""
    text = text.replace("\n", " ")
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _write(out: list[str], depth: int, kind: str, detail: str, span: object) -> None:
    suffix = f"  [{span}]" if span is not None else ""
    out.append(f"{'  ' * depth}{kind} {detail}{suffix}\n")
