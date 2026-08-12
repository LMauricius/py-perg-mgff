"""`pyperg generate`: run a backend over a grammar."""

from __future__ import annotations

import argparse
from pathlib import Path

from ...diagnostics.source import SourceFile
from ...generators import registry
from ...mgff.itemizing.itemizer import itemize
from ...mgff.systems.model import parse, rule_tree_factory, resolve
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
            for name, backend in sorted(registry.available_generators().items()):
                print(f"{name:12} {backend.description}")
            return 0

        if cli_args.file is None:
            print("generate: a file is required unless --list is given")
            return 2

        # 1. Look the backend up first: the constructs it registers are in force
        #    while the grammar is read, so they must be known before resolving.
        backend = registry.load_generator(cli_args.generator)

        # 2. Lex, parse and resolve the file into a model.
        source = SourceFile.read_from_path(cli_args.file)
        fileScope = parse(itemize(source), rule_tree_factory)
        model = resolve(fileScope, name=source.name, macros=backend.macros())

        # 3. Run the backend over the model.
        written_paths = backend.generate(model, Path(cli_args.out_dir))

        # 4. Print the paths written.
        for path in written_paths:
            print(path)
        return 0
