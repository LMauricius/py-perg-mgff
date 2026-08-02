"""`pyperg check`: read a grammar and report its errors, generating nothing.

Parts 1 and 2 are checked; reading the items by shape is Part 3 and still to come.
"""

from __future__ import annotations

import argparse

from ...diagnostics.source import SourceFile
from ...grammar.parser import parse
from ...grammar.scope import Scope
from ...mgff.lexer import lex
from .base import Command


def _count(scope: Scope) -> tuple[int, int]:
    """The macros and targets of a scope tree, counting each definition once."""
    macros = sum(1 for macro in scope.sources.values() if macro.scope is scope)
    targets = len(scope.targets)
    for child in list(scope.subscopes.values()) + list(scope.targets.values()):
        # Skip what a prefix scope handed up; it is counted where it was defined.
        if child.parent is not scope:
            continue
        child_macros, child_targets = _count(child)
        macros += child_macros
        targets += child_targets
    return macros, targets


class CheckCommand(Command):
    name = "check"
    help = "validate a grammar without generating anything"

    def add_cli_arguments(self, cli_parser: argparse.ArgumentParser) -> None:
        cli_parser.add_argument("file", help="the MGFF file to check")

    def run(self, cli_args: argparse.Namespace) -> int:
        # Errors of either part are raised here and reported by `cli.main`.
        source = SourceFile.read(cli_args.file)
        root = parse(lex(source))

        macros, targets = _count(root)
        print(f"{source.name}: ok, {macros} macros, {targets} targets")
        return 0
