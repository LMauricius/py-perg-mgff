"""A backend writing a TextMate grammar, packaged for Visual Studio Code.

TextMate grammars are what VS Code highlights with — its engine reads nothing
else — and the same format is understood by Sublime Text, Atom's descendants,
GitHub's linguist and shiki. See `Docs/textmate-generator.md`.

Highlighting is only part of what VS Code calls language support, and the rest
comes from files beside the grammar, so one grammar gives a folder that is a
working extension:

    package.json                  what the language is called, and what it owns
    language-configuration.json    brackets, folding, auto-closing, comments
    syntaxes/<Name>.tmLanguage.json  the grammar itself

Point VS Code at the folder — `code --extensionDevelopmentPath=<out>` — or copy
it into `~/.vscode/extensions/`. A project that only wants the grammar can take
the one file and ignore the other two.

**Brackets come from the grammar.** VS Code folds, matches and auto-closes by
the pairs in `language-configuration.json`, not by anything in the TextMate
grammar, so the bracketing productions `repository` finds are written into both:
into the grammar as the spans they highlight, and into the configuration as the
pairs the editor folds.
"""

from __future__ import annotations

import json
from pathlib import Path

from ...mgff.semantics.model import GrammarModel
from ..base import Generator
from ..utils.naming import pascal_case, safe_identifier
from .repository import RepositoryBuilder

#: The attribute-only macro a grammar describes itself with.
METADATA_MACRO = "Language"

#: Where the grammar sits inside the generated extension.
SYNTAXES_DIR = "syntaxes"

#: What the generated `package.json` claims to need.
VSCODE_ENGINE = "^1.75.0"


def _setting(metadata: dict[str, list[str]], key: str, default: str | None) -> str | None:
    """One value from the `Language` macro, or a default.

    An attribute written with several arguments joins them with a space, the
    same way the Kate backend reads one.
    """


def _values(metadata: dict[str, list[str]], key: str) -> list[str]:
    """Every argument of one `Language` attribute, or an empty list."""


class TextMateGenerator(Generator):
    """Writes a TextMate grammar and the files VS Code needs beside it."""

    name = "textmate"
    description = "write a TextMate grammar, packaged as a VS Code extension"

    def generate(self, model: GrammarModel, out_dir: Path) -> list[Path]:
        """Write the three files and return their paths, grammar first."""
        # syntaxes/<Name>.tmLanguage.json, language-configuration.json, package.json

    # -- naming ------------------------------------------------------------

    def language_name(self, model: GrammarModel) -> str:
        """What the language is called, as a person reads it.

        From `d Language > name(…)`, and from the grammar file's own name
        otherwise, exactly as the Kate backend decides it.
        """

    def language_id(self, model: GrammarModel) -> str:
        """The identifier VS Code files the language under, and every scope ends in.

        Lower case with no punctuation, since a scope name is read as a dotted
        path and an identifier is compared verbatim.
        """

    def scope_name(self, model: GrammarModel) -> str:
        """The grammar's own scope, which must be unique across installed grammars.

        `source.<id>` by convention for a programming language; a grammar
        describing markup says `d Language > scope(text.<id>)` instead.
        """

    def extensions(self, model: GrammarModel) -> list[str]:
        """The file extensions the language claims, as VS Code spells them.

        `extensions(*.toy *.t)` reaches Kate as a glob and VS Code as `.toy`,
        `.t`, so the leading star is dropped and a bare name gains a dot.
        """

    # -- the grammar -------------------------------------------------------

    def builder(self, model: GrammarModel) -> RepositoryBuilder:
        """The repository, built once so the grammar and the brackets agree."""

    def grammar(self, model: GrammarModel) -> dict:
        """The `.tmLanguage.json` object: what it is called, and what it matches."""
        # scopeName, name, patterns, repository, and fileTypes for the readers
        # that use it (linguist, shiki) even though VS Code takes it from package.json

    def render(self, model: GrammarModel) -> str:
        """The grammar as JSON text, without touching the file system."""

    # -- the extension around it -------------------------------------------

    def language_configuration(self, model: GrammarModel) -> dict:
        """Brackets, folding, auto-closing and comment markers.

        The bracket pairs are the bracketing productions the repository found.
        Comment markers are not derived — a grammar that wants comment toggling
        says `d Language > lineComment(#)` — because a `Comment` production's
        leading literal is a guess and a wrong one is worse than none.
        """
        # comments from lineComment / blockComment, then brackets ->
        # brackets, autoClosingPairs, surroundingPairs

    def package(self, model: GrammarModel) -> dict:
        """The extension manifest tying the language to its grammar."""
        # name, displayName, version, engines, categories,
        # contributes.languages + contributes.grammars
