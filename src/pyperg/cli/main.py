"""The `pyperg` entry point: argument parsing and dispatch."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from .. import __version__
from ..diagnostics.errors import PyPergError, SourceError
from ..diagnostics.reporter import print_error
from ..diagnostics.source import SourceFile
from .commands import COMMANDS


def build_cli_parser() -> argparse.ArgumentParser:
    """The root parser, with one subparser per command."""
    cli_parser = argparse.ArgumentParser(
        prog="pyperg",
        description=(
            "Parser Environment Regenerator: "
            "generate lexers and parsers from MGFF grammars."
        ),
    )
    cli_parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )

    cli_subparsers = cli_parser.add_subparsers(dest="command", metavar="COMMAND")
    for command in COMMANDS:
        command.add_cli_subparser(cli_subparsers)
    return cli_parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run a command. Returns the process exit status."""
    cli_parser = build_cli_parser()
    cli_args = cli_parser.parse_args(argv)

    if not hasattr(cli_args, "_run"):
        cli_parser.print_help()
        return 2

    try:
        return cli_args._run(cli_args)
    except PyPergError as error:
        # Reload the file so the diagnostic can quote the offending line.
        source = None
        if isinstance(error, SourceError) and getattr(cli_args, "file", None):
            try:
                source = SourceFile.read_from_path(cli_args.file)
            except OSError:
                source = None
        print_error(error, source)
        return 1
    except OSError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    except UnicodeDecodeError:
        # An MGFF file is UTF-8 text; anything else is a file we were handed by
        # mistake, and saying so beats a decoder's traceback.
        file_label = getattr(cli_args, "file", None) or "input"
        print(f"error: {file_label}: not valid UTF-8", file=sys.stderr)
        return 1
    except RecursionError:
        # The lexer bounds how deeply groups may nest, and the generators bound
        # the states they build; this is the backstop for the walks that do not.
        print(
            "error: the grammar nests too deeply to be read",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
