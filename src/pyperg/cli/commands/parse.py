"""`pyperg parse`: show the scopes, targets and macros of a grammar (Part 2)."""

from __future__ import annotations

import argparse

from ...diagnostics.source import SourceFile
from ...grammar.parser import parse
from ...grammar.scope import MacroSource, Scope
from ...mgff.cst import Item, render_item
from ...mgff.lexer import lex
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
        source = SourceFile.read(cli_args.file)
        root = parse(lex(source))
        print(
            _render_scope(root, source.name, cli_args.spans, cli_args.absorbed),
            end="",
        )
        return 0


# -- rendering -------------------------------------------------------------


def _render_scope(root: Scope, name: str, spans: bool, absorbed: bool) -> str:
    out: list[str] = [f"file {name}\n"]
    _render_body(root, depth=1, out=out, spans=spans, absorbed=absorbed)
    return "".join(out)


def _render_body(scope: Scope, depth: int, out: list[str], spans: bool, absorbed: bool) -> None:
    for key, macro in scope.sources.items():
        # A macro whose key is not its own signature was absorbed from a prefix
        # scope, so it is already listed there under its local name.
        if macro.scope is not scope and not absorbed:
            continue
        _render_macro(key, macro, depth, out, spans)

    for key, child in scope.subscopes.items():
        if child.parent is not scope and not absorbed:
            continue
        _write(out, depth, "prefix", key, child.span if spans else None)
        _render_body(child, depth + 1, out, spans, absorbed)

    for target in scope.targets.values():
        _write(out, depth, "target", target.name, target.span if spans else None)
        _render_body(target, depth + 1, out, spans, absorbed)


def _render_macro(key: str, macro: MacroSource, depth: int, out: list[str], spans: bool) -> None:
    detail = key
    if macro.parameters:
        detail += f"  ({', '.join(macro.parameters)})"
    _write(out, depth, "macro", detail, macro.span if spans else None)

    marker = macro.choice_symbol or "="
    for option in macro.options:
        _write(out, depth + 1, marker, _render_items(option), None)
    for attributes in macro.attribute_lists:
        _write(out, depth + 1, ">", _render_items(attributes), None)


def _render_items(items: list[Item]) -> str:
    """One line of an option or an attribute list, as it was written."""
    return " ".join(render_item(item) for item in items) or "(empty)"


def _write(out: list[str], depth: int, kind: str, detail: str, span: object) -> None:
    suffix = f"  [{span}]" if span is not None else ""
    out.append(f"{'  ' * depth}{kind} {detail}{suffix}\n")
