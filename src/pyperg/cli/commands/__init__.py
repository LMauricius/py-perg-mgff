"""The subcommands.

Each is a `Command` subclass. Adding a subcommand means adding a class and
listing an instance of it in `COMMANDS`.
"""

from .base import Command
from .check import CheckCommand
from .generate import GenerateCommand
from .lex import LexCommand
from .parse import ParseCommand

COMMANDS: list[Command] = [LexCommand(), ParseCommand(), CheckCommand(), GenerateCommand()]

__all__ = ["COMMANDS", "Command"]
