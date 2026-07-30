"""The common shape of a subcommand."""

from __future__ import annotations

import abc
import argparse
from typing import ClassVar


class Command(abc.ABC):
    """One `pyperg` subcommand.

    Subclasses set `name` and `help`, add their own options in
    `add_arguments`, and do the work in `run`.
    """

    name: ClassVar[str]
    help: ClassVar[str]

    def add_cli_subparser(
        self, cli_subparsers: argparse._SubParsersAction
    ) -> argparse.ArgumentParser:
        """Register this command's subparser and its options."""
        cli_subparser: argparse.ArgumentParser = cli_subparsers.add_parser(
            self.name, help=self.help, description=self.help
        )
        self.add_cli_arguments(cli_subparser)
        cli_subparser.set_defaults(_run=self.run)
        return cli_subparser

    def add_cli_arguments(self, cli_parser: argparse.ArgumentParser) -> None:
        """Declare the command's arguments. Commands without options need not override."""

    @abc.abstractmethod
    def run(self, cli_args: argparse.Namespace) -> int:
        """Do the work. Returns the process exit status."""
