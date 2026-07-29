"""The subcommands.

Each module here exposes `NAME`, `HELP`, `add_parser(subparsers)` and
`run(args) -> int`. Adding a subcommand means adding a module and listing it in
`COMMANDS`.
"""

from types import ModuleType

from . import check, generate, lex

COMMANDS: list[ModuleType] = [lex, check, generate]

__all__ = ["COMMANDS"]
