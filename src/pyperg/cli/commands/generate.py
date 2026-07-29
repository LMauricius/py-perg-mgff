"""`pyperg generate`: run a backend over a grammar.

Backend listing works; generation waits on the front end.
"""

from __future__ import annotations

import argparse

from ...generators import registry

NAME = "generate"
HELP = "generate a lexer and parser from a grammar"


def add_parser(subparsers: argparse._SubParsersAction) -> argparse.ArgumentParser:
    parser = subparsers.add_parser(NAME, help=HELP, description=HELP)
    parser.add_argument("file", nargs="?", help="the MGFF file to generate from")
    parser.add_argument("-g", "--generator", default="python", help="the backend to use")
    parser.add_argument("-o", "--out-dir", default=".", help="where to write the output")
    parser.add_argument(
        "--list", action="store_true", help="list the available backends and exit"
    )
    return parser


def run(args: argparse.Namespace) -> int:
    if args.list:
        for name, backend in sorted(registry.available().items()):
            print(f"{name:12} {backend.description}")
        return 0

    if args.file is None:
        print("generate: a file is required unless --list is given")
        return 2

    # 1. Lex, parse and resolve the file into a model.
    # 2. Look the backend up in the registry and run it over the model.
    # 3. Print the paths written.
    print("generate: not implemented yet")
    return 2
