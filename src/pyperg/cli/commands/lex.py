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
        source = SourceFile.read_from_path(cli_args.file)
        tree = lex(source)
        print(
            _render_file(
                tree,
                show_spans=cli_args.spans,
                show_blank_lines=cli_args.blank_lines,
            ),
            end="",
        )
        return 0


# -- rendering -------------------------------------------------------------


def _render_file(file: File, show_spans: bool, show_blank_lines: bool) -> str:
    output_lines: list[str] = [f"file {file.name}\n"]
    _render_lines(
        file.lines,
        depth=1,
        output_lines=output_lines,
        show_spans=show_spans,
        show_blank_lines=show_blank_lines,
    )
    return "".join(output_lines)


def _render_lines(
    lines: list[Line],
    depth: int,
    output_lines: list[str],
    show_spans: bool,
    show_blank_lines: bool,
) -> None:
    for line in lines:
        if line.is_blank and not show_blank_lines:
            continue
        _append_tree_line(
            output_lines,
            depth,
            "line",
            f"({len(line.items)} items)",
            line.span if show_spans else None,
        )
        for item in line.items:
            _render_item(item, depth + 1, output_lines, show_spans, show_blank_lines)


def _render_item(
    item: Item,
    depth: int,
    output_lines: list[str],
    show_spans: bool,
    show_blank_lines: bool,
) -> None:
    _append_tree_line(
        output_lines,
        depth,
        "item",
        _shorten_to_one_line(render_item(item)),
        item.span if show_spans else None,
    )
    for part in item.parts:
        if isinstance(part, Text):
            _append_tree_line(
                output_lines,
                depth + 1,
                "text",
                repr(part.value),
                part.span if show_spans else None,
            )
        else:
            _render_group(part, depth + 1, output_lines, show_spans, show_blank_lines)


def _render_group(
    group: Group,
    depth: int,
    output_lines: list[str],
    show_spans: bool,
    show_blank_lines: bool,
) -> None:
    _append_tree_line(
        output_lines,
        depth,
        "group",
        f"({len(group.lines)} lines)",
        group.span if show_spans else None,
    )
    _render_lines(group.lines, depth + 1, output_lines, show_spans, show_blank_lines)


def _shorten_to_one_line(text: str, limit: int = 60) -> str:
    """Shorten the one-line summary of an item; its parts follow underneath anyway."""
    text = text.replace("\n", " ")
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _append_tree_line(
    output_lines: list[str],
    depth: int,
    node_kind: str,
    detail: str,
    span: object,
) -> None:
    suffix = f"  [{span}]" if span is not None else ""
    output_lines.append(f"{'  ' * depth}{node_kind} {detail}{suffix}\n")
