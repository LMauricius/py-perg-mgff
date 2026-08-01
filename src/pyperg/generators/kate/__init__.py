"""A backend writing a KDE syntax definition.

The output is the XML format Kate, KWrite and KDevelop read for syntax
highlighting, and the same format pandoc's skylighting reads for fenced code
blocks. See `Docs/kate-generator.md` for what the grammar has to look like and
what each attribute does.
"""

from __future__ import annotations

from pathlib import Path

from ...semantics.model import GrammarModel
from ..base import Generator
from ..utils.emit import Emitter
from ..utils.naming import pascal_case, safe_identifier
from ..utils.xmlwrite import Element
from .contexts import LEX_TARGET, PARSE_TARGET, ContextBuilder

#: The attribute-only macro a grammar describes itself with.
METADATA_MACRO = "Language"

#: The version of Kate's format the output declares.
KATE_VERSION = "5.79"

_HEADER = '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE language SYSTEM "language.dtd">'


def _setting(metadata: dict[str, list[str]], key: str, default: str | None) -> str | None:
    """One value from the `Language` macro, or a default.

    An attribute written with several arguments joins them with a space, so
    `extensions(*.calc *.c1)` reaches Kate as the list it looks like.
    """
    values = metadata.get(key)
    return " ".join(values) if values else default


class KateGenerator(Generator):
    """Writes one KDE syntax definition, covering `Lex` and `Parse`."""

    name = "kate"
    description = "write a KDE/Kate syntax definition, also read by pandoc"

    def generate(self, model: GrammarModel, out_dir: Path) -> list[Path]:
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"{self.language_name(model)}.xml"
        path.write_text(self.render(model), encoding="utf-8")
        return [path]

    def supports_target(self, target: str) -> bool:
        return target in (LEX_TARGET, PARSE_TARGET)

    # -- naming ------------------------------------------------------------

    def language_name(self, model: GrammarModel) -> str:
        """What the highlighted language is called.

        Taken from `d Language > name(…)` when the grammar says so, and from the
        grammar file's own name otherwise.
        """
        metadata = model.metadata.get(METADATA_MACRO, {})
        # The words of a file name come first, so `my-toy.mgff` gives `MyToy`
        # rather than a spelled-out hyphen.
        return _setting(metadata, "name", None) or safe_identifier(
            pascal_case(Path(model.name).stem), fallback="Grammar"
        )

    # -- rendering ---------------------------------------------------------

    def render(self, model: GrammarModel) -> str:
        """Render the syntax definition without touching the file system."""
        builder = ContextBuilder(model)
        builder.build()
        contexts, item_datas, lists = builder.elements()

        root = self.language_element(model)
        highlighting = root.child("highlighting")
        highlighting.children.extend(lists)
        highlighting.child("contexts").children.extend(contexts)
        highlighting.child("itemDatas").children.extend(item_datas)
        self.general_element(root, model)

        out = Emitter()
        out.line(_HEADER)
        root.write(out)
        return out.render()

    def language_element(self, model: GrammarModel) -> Element:
        """The root element, carrying everything Kate files the language under."""
        metadata = model.metadata.get(METADATA_MACRO, {})
        name = self.language_name(model)
        attributes = {
            "name": name,
            "version": _setting(metadata, "version", "1"),
            "kateversion": _setting(metadata, "kateversion", KATE_VERSION),
            "section": _setting(metadata, "section", "Sources"),
            "extensions": _setting(metadata, "extensions", f"*.{name.lower()}"),
            "mimetype": _setting(metadata, "mimetype", None),
            "author": _setting(metadata, "author", None),
            "license": _setting(metadata, "license", None),
            "priority": _setting(metadata, "priority", None),
        }
        return Element(
            "language", {key: value for key, value in attributes.items() if value is not None}
        )

    def general_element(self, root: Element, model: GrammarModel) -> None:
        """The `<general>` block, which is where keyword matching is tuned.

        MGFF has no spelling for case-insensitive matching, so keywords are
        case-sensitive unless the grammar says otherwise.
        """
        metadata = model.metadata.get(METADATA_MACRO, {})
        general = root.child("general")
        general.child(
            "keywords",
            casesensitive=_setting(metadata, "casesensitive", "1"),
            weakDeliminator=_setting(metadata, "weakDeliminator", None),
            additionalDeliminator=_setting(metadata, "additionalDeliminator", None),
        )
