"""The subcommands.

Each is a `Command` subclass. Adding a subcommand means adding a class and
listing an instance of it in `COMMANDS`.
"""

from .base import Command
from .check import CheckCommand
from .generate import GenerateCommand
from .debug import DebugCommand

COMMANDS: list[Command] = [DebugCommand(), CheckCommand(), GenerateCommand()]

__all__ = ["COMMANDS", "Command"]
