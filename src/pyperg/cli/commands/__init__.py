"""The subcommands.

Each is a `Command` subclass. Adding a subcommand means adding a class and
listing an instance of it in `COMMANDS`.
"""

from .base import Command
from .check import CheckCommand
from .generate import GenerateCommand
from .lex import LexCommand

COMMANDS: list[Command] = [LexCommand(), CheckCommand(), GenerateCommand()]

__all__ = ["COMMANDS", "Command"]
