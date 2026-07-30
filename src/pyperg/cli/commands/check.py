"""`pyperg check`: read a grammar and report its errors, generating nothing.

The reading itself is not implemented yet.
"""

from __future__ import annotations

import argparse

from .base import Command


class CheckCommand(Command):
    name = "check"
    help = "validate a grammar without generating anything"

    def add_cli_arguments(self, cli_parser: argparse.ArgumentParser) -> None:
        cli_parser.add_argument("file", help="the MGFF file to check")

    def run(self, cli_args: argparse.Namespace) -> int:
        # 1. Lex the file (Part 1).
        # 2. Parse it into a grammar (Part 2).
        # 3. Resolve it into a model, reporting every error found.
        print("check: not implemented yet")
        return 2
