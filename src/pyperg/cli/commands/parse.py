"""`pyperg parse`: show the scopes, targets and macros of a grammar (Part 2)."""

from __future__ import annotations

import argparse

from ...diagnostics.source import SourceFile
from ...mgff.grammar.parser import parse
from ...mgff.grammar.scope import MacroSource, Scope
from ...mgff.lexing.cst import Item, render_item
from ...mgff.lexing.lexer import lex
from .base import Command


class ParseCommand(Command):
    name = "parse"
    help = "show the scopes, targets and macros a file defines"

    def add_cli_arguments(self, cli_parser: argparse.ArgumentParser) -> None:
        cli_parser.add_argument("file", help="the MGFF file to read")
        cli_parser.add_argument(
            "--spans",
            action="store_true",
            help="annotate every macro with its source span",
        )
        cli_parser.add_argument(
            "--absorbed",
            action="store_true",
            help="show the prefixed names a scope took from its prefix scopes",
        )

    def run(self, cli_args: argparse.Namespace) -> int:
        source = SourceFile.read_from_path(cli_args.file)
        root = parse(lex(source))
        print(
            _render_scope(root, source.name, cli_args.spans, cli_args.absorbed),
            end="",
        )
        return 0


# -- rendering -------------------------------------------------------------


def _render_scope(root: Scope, name: str, show_spans: bool, show_absorbed: bool) -> str:
    output_lines: list[str] = [f"file {name}\n"]
    _render_body(
        root,
        depth=1,
        output_lines=output_lines,
        show_spans=show_spans,
        show_absorbed=show_absorbed,
    )
    return "".join(output_lines)


def _render_body(
    scope: Scope,
    depth: int,
    output_lines: list[str],
    show_spans: bool,
    show_absorbed: bool,
) -> None:
    if scope.attribute_list:
        _append_tree_line(
            output_lines,
            depth,
            ">",
            _render_items_as_line(scope.attribute_list),
            None,
        )

    for signature, macro in scope.sources.items():
        # A macro whose key is not its own signature was absorbed from a prefix
        # scope, so it is already listed there under its local name.
        if macro.scope is not scope and not show_absorbed:
            continue
        _render_macro(signature, macro, depth, output_lines, show_spans)

    for prefix_name, child in scope.subscopes.items():
        if child.parent is not scope and not show_absorbed:
            continue
        _append_tree_line(
            output_lines,
            depth,
            "prefix",
            prefix_name,
            child.span if show_spans else None,
        )
        _render_body(child, depth + 1, output_lines, show_spans, show_absorbed)

    for target in scope.targets.values():
        _append_tree_line(
            output_lines,
            depth,
            "target",
            target.name,
            target.span if show_spans else None,
        )
        _render_body(target, depth + 1, output_lines, show_spans, show_absorbed)


def _render_macro(
    signature: str,
    macro: MacroSource,
    depth: int,
    output_lines: list[str],
    show_spans: bool,
) -> None:
    detail = signature
    if macro.parameters:
        detail += f"  ({', '.join(macro.parameters)})"
    _append_tree_line(
        output_lines,
        depth,
        "macro",
        detail,
        macro.span if show_spans else None,
    )

    option_marker = macro.choice_symbol or "="
    for option in macro.options:
        _append_tree_line(
            output_lines,
            depth + 1,
            option_marker,
            _render_items_as_line(option),
            None,
        )
    for attributes in macro.attribute_lists:
        _append_tree_line(
            output_lines,
            depth + 1,
            ">",
            _render_items_as_line(attributes),
            None,
        )


def _render_items_as_line(items: list[Item]) -> str:
    """One line of an option or an attribute list, as it was written."""
    return " ".join(render_item(item) for item in items) or "(empty)"


def _append_tree_line(
    output_lines: list[str],
    depth: int,
    node_kind: str,
    detail: str,
    span: object,
) -> None:
    suffix = f"  [{span}]" if span is not None else ""
    output_lines.append(f"{'  ' * depth}{node_kind} {detail}{suffix}\n")
