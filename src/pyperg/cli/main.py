"""The `pyperg` entry point: argument parsing and dispatch."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from .. import __version__
from ..diagnostics.errors import PyPergError, SourceError
from ..diagnostics.reporter import report
from ..diagnostics.source import SourceFile
from .commands import COMMANDS


def build_parser() -> argparse.ArgumentParser:
    """The root parser, with one subparser per command module."""
    parser = argparse.ArgumentParser(
        prog="pyperg",
        description="Parser Environment Regenerator: generate lexers and parsers from MGFF grammars.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")
    for module in COMMANDS:
        module.add_parser(subparsers).set_defaults(_run=module.run)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run a command. Returns the process exit status."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if not hasattr(args, "_run"):
        parser.print_help()
        return 2

    try:
        return args._run(args)
    except PyPergError as err:
        # Reload the file so the diagnostic can quote the offending line.
        source = None
        if isinstance(err, SourceError) and getattr(args, "file", None):
            try:
                source = SourceFile.read(args.file)
            except OSError:
                source = None
        report(err, source)
        return 1
    except OSError as err:
        print(f"error: {err}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
