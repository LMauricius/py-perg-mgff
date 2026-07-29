"""`pyperg check`: read a grammar and report its errors, generating nothing.

The reading itself is not implemented yet.
"""

from __future__ import annotations

import argparse

NAME = "check"
HELP = "validate a grammar without generating anything"


def add_parser(subparsers: argparse._SubParsersAction) -> argparse.ArgumentParser:
    parser = subparsers.add_parser(NAME, help=HELP, description=HELP)
    parser.add_argument("file", help="the MGFF file to check")
    return parser


def run(args: argparse.Namespace) -> int:
    # 1. Lex the file (Part 1).
    # 2. Parse it into a grammar (Part 2).
    # 3. Resolve it into a model, reporting every error found.
    print("check: not implemented yet")
    return 2
