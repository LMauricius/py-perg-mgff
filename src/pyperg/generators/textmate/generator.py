"""A backend writing a TextMate grammar, packaged for Visual Studio Code.

TextMate grammars are what VS Code highlights with — its engine reads nothing
else — and the same format is understood by Sublime Text, Zed, GitHub's linguist
and shiki. See `Docs/textmate-generator.md`.

Highlighting is only part of what VS Code calls language support, and the rest
comes from files beside the grammar, so one grammar gives a folder that is a
working extension:

    package.json                     what the language is called, and what it owns
    language-configuration.json      brackets, folding, auto-closing, comments
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

from ...diagnostics.errors import GeneratorError
from ...mgff.systems.model import GrammarModel
from ..base import Generator
from ..utils.naming import pascal_case, safe_file_name, safe_identifier, words_of
from ..utils.settings import setting_value, setting_values
from .repository import RepositoryBuilder

#: Where the grammar sits inside the generated extension.
SYNTAXES_DIR = "syntaxes"

#: The files written beside it.
CONFIGURATION_FILE = "language-configuration.json"
MANIFEST_FILE = "package.json"

#: What the generated manifest claims to need. Anything from this release on
#: reads the grammar and the configuration the same way.
VSCODE_ENGINE = "^1.75.0"

#: The schema VS Code offers completion against while a grammar is edited.
GRAMMAR_SCHEMA = (
    "https://raw.githubusercontent.com/martinring/tmlanguage/master/tmlanguage.json"
)


def _write_json(path: Path, data: dict) -> None:
    """Write one object, indented the way VS Code's own files are."""
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def _semantic_version(value: str) -> str:
    """A version an extension manifest will accept.

    Kate is happy with `version(1)` and a manifest is not, so a grammar that
    describes itself once for both backends has its version padded out rather
    than rejected. Anything that is not a run of numbers is passed through, on
    the grounds that whoever wrote it meant it.
    """
    parts = value.split(".")
    if len(parts) < 3 and all(part.isdigit() for part in parts):
        return ".".join([*parts, *["0"] * (3 - len(parts))])
    return value


def _file_type(extension: str) -> str:
    """One declared extension without its glob or its dot, as `fileTypes` wants."""
    return extension.lstrip("*").lstrip(".")


class TextMateGenerator(Generator):
    """Writes a TextMate grammar and the files VS Code needs beside it."""

    name = "textmate"
    description = "write a TextMate grammar, packaged as a VS Code extension"

    def generate(self, model: GrammarModel, out_dir: Path) -> list[Path]:
        """Write the three files and return their paths, the grammar first."""
        # The repository is built once: it warns about what it skips, and the
        # brackets the configuration folds must be the ones the grammar found.
        builder = self.builder(model)
        syntaxes = out_dir / SYNTAXES_DIR
        syntaxes.mkdir(parents=True, exist_ok=True)

        grammar = syntaxes / f"{self.grammar_stem(model)}.tmLanguage.json"
        configuration = out_dir / CONFIGURATION_FILE
        manifest = out_dir / MANIFEST_FILE
        _write_json(grammar, self.grammar(model, builder))
        _write_json(configuration, self.language_configuration(model, builder))
        _write_json(manifest, self.package(model))
        return [grammar, configuration, manifest]

    # -- naming ------------------------------------------------------------

    def language_name(self, model: GrammarModel) -> str:
        """What the language is called, as a person reads it.

        From the file's own `> name(…)`, and from the grammar file's name
        otherwise, exactly as the Kate backend decides it.
        """
        return setting_value(model.attributes, "name", None) or safe_identifier(
            pascal_case(Path(model.name).stem), fallback="Grammar"
        )

    def grammar_stem(self, model: GrammarModel) -> str:
        """What the grammar file is called, which is a name and not a path.

        The grammar names itself, and that name reaches the file system here and
        in the manifest that points at it, so it names a file inside the output
        directory and nothing outside it.
        """
        return safe_file_name(self.language_name(model))

    def language_id(self, model: GrammarModel) -> str:
        """The identifier VS Code files the language under, and every scope ends in.

        Lower case and hyphenated, since a scope name is a dotted path and an
        identifier is compared verbatim. The name is split into words at case
        changes too, so `MyToy` gives `my-toy` rather than `mytoy`.
        """
        given = setting_value(model.attributes, "id", None)
        if given:
            return given
        words = words_of(self.language_name(model))
        return "-".join(word.lower() for word in words) or "grammar"

    def scope_name(self, model: GrammarModel) -> str:
        """The grammar's own scope, which must be unique across installed grammars.

        `source.<id>` by convention for a programming language; a grammar
        describing markup writes `> scope(text.<id>)` at its top instead.
        """
        return (
            setting_value(model.attributes, "scope", None)
            or f"source.{self.language_id(model)}"
        )

    def extensions(self, model: GrammarModel) -> list[str]:
        """The file extensions the language claims, as VS Code spells them.

        `extensions(*.toy *.t)` reaches Kate as a glob and VS Code as `.toy`,
        `.t`, so the leading star is dropped and a bare name gains a dot.
        """
        declared = setting_values(model.attributes, "extensions") or [
            f".{self.language_id(model)}"
        ]
        return [f".{_file_type(extension)}" for extension in declared]

    # -- the grammar -------------------------------------------------------

    def builder(self, model: GrammarModel) -> RepositoryBuilder:
        """The repository, built once so the grammar and the brackets agree."""
        builder = RepositoryBuilder(model, self.language_id(model))
        builder.build()
        return builder

    def grammar(self, model: GrammarModel, builder: RepositoryBuilder) -> dict:
        """The `.tmLanguage.json` object: what it is called, and what it matches.

        `fileTypes` is for the readers that take the grammar on its own — shiki,
        linguist, Sublime Text. VS Code ignores it and reads the manifest.
        """
        return {
            "$schema": GRAMMAR_SCHEMA,
            "name": self.language_name(model),
            "scopeName": self.scope_name(model),
            "fileTypes": [_file_type(one) for one in self.extensions(model)],
            "patterns": builder.top_patterns(),
            "repository": builder.repository(),
        }

    def render(self, model: GrammarModel) -> str:
        """The grammar as JSON text, without touching the file system."""
        return json.dumps(
            self.grammar(model, self.builder(model)), indent=2, ensure_ascii=False
        )

    # -- the extension around it -------------------------------------------

    def language_configuration(
        self, model: GrammarModel, builder: RepositoryBuilder
    ) -> dict:
        """Brackets, folding, auto-closing and comment markers.

        The bracket pairs are the bracketing productions the repository found,
        which is what makes VS Code fold and auto-close what the grammar nests.

        Comment markers are not derived. A `Comment` production's leading
        literal looks like a line-comment marker and often is not — a block
        comment opens the same way — and toggling with the wrong marker damages
        a file, so the grammar has to say `> lineComment(#)` at its top.
        """
        configuration: dict = {}

        comments: dict = {}
        line = setting_value(model.attributes, "lineComment", None)
        if line:
            comments["lineComment"] = line
        block = setting_values(model.attributes, "blockComment")
        if block:
            if len(block) != 2:
                raise GeneratorError(
                    "`blockComment` takes the opening and the closing marker, as in "
                    f"`blockComment(/* */)`; this one has {len(block)} argument(s)"
                )
            comments["blockComment"] = block
        if comments:
            configuration["comments"] = comments

        pairs = builder.bracket_pairs()
        if pairs:
            configuration["brackets"] = [
                [opening, closing] for opening, closing in pairs
            ]
            configuration["autoClosingPairs"] = [
                {"open": opening, "close": closing} for opening, closing in pairs
            ]
            configuration["surroundingPairs"] = [
                [opening, closing] for opening, closing in pairs
            ]
        return configuration

    def package(self, model: GrammarModel) -> dict:
        """The extension manifest tying the language to its grammar."""
        name = self.language_name(model)
        identifier = self.language_id(model)

        language: dict = {
            "id": identifier,
            "aliases": [name, identifier],
            "extensions": self.extensions(model),
            "configuration": f"./{CONFIGURATION_FILE}",
        }
        mimetypes = setting_values(model.attributes, "mimetype")
        if mimetypes:
            language["mimetypes"] = mimetypes

        manifest: dict = {
            "name": identifier,
            "displayName": name,
            "description": setting_value(
                model.attributes, "description", f"{name} language support."
            ),
            "version": _semantic_version(
                setting_value(model.attributes, "version", None) or "0.0.1"
            ),
            "engines": {"vscode": VSCODE_ENGINE},
            "categories": ["Programming Languages"],
            "contributes": {
                "languages": [language],
                "grammars": [
                    {
                        "language": identifier,
                        "scopeName": self.scope_name(model),
                        "path": (
                            f"./{SYNTAXES_DIR}/"
                            f"{self.grammar_stem(model)}.tmLanguage.json"
                        ),
                    }
                ],
            },
        }
        for key in ("publisher", "license"):
            value = setting_value(model.attributes, key, None)
            if value:
                manifest[key] = value
        return manifest
