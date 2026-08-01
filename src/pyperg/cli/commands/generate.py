"""`pyperg generate`: run a backend over a grammar."""

from __future__ import annotations

import argparse
from pathlib import Path

from ...diagnostics.source import SourceFile
from ...generators import registry
from ...grammar.parser import parse
from ...mgff.lexer import lex
from ...semantics.model import resolve
from .base import Command

class GenerateCommand(Command):
    name = "generate"
    help = "generate a lexer and parser from a grammar"

    def add_cli_arguments(self, cli_parser: argparse.ArgumentParser) -> None:
        cli_parser.add_argument(
            "file", nargs="?", help="the MGFF file to generate from"
        )
        cli_parser.add_argument(
            "-g", "--generator", default="python", help="the backend to use"
        )
        cli_parser.add_argument(
            "-o", "--out-dir", default=".", help="where to write the output"
        )
        cli_parser.add_argument(
            "--list", action="store_true", help="list the available backends and exit"
        )

    def run(self, cli_args: argparse.Namespace) -> int:
        if cli_args.list:
            for name, backend in sorted(registry.available().items()):
                print(f"{name:12} {backend.description}")
            return 0

        if cli_args.file is None:
            print("generate: a file is required unless --list is given")
            return 2

        # 1. Lex, parse and resolve the file into a model.
        source = SourceFile.read(cli_args.file)
        model = resolve(parse(lex(source)), name=source.name)

        # 2. Look the backend up in the registry and run it over the model.
        backend = registry.get(cli_args.generator)
        written = backend.generate(model, Path(cli_args.out_dir))

        # 3. Print the paths written.
        for path in written:
            print(path)
        return 0
