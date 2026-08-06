"""A backend writing a KDE syntax definition.

The output is the XML format Kate, KWrite and KDevelop read for syntax
highlighting, and the same format pandoc's skylighting reads for fenced code
blocks. See `Docs/kate-generator.md` for what the grammar has to look like and
what each attribute does.
"""

from __future__ import annotations

from pathlib import Path

from ...mgff.semantics.model import GrammarModel
from ..base import Generator
from ..utils.emit import Emitter
from ..utils.naming import pascal_case, safe_identifier
from ..utils.settings import setting
from ..utils.xmlwrite import Element
from .contexts import ContextBuilder

#: The version of Kate's format the output declares.
KATE_VERSION = "5.79"

_HEADER = '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE language SYSTEM "language.dtd">'


class KateGenerator(Generator):
    """Writes one KDE syntax definition, covering `Lex` and `Parse`."""

    name = "kate"
    description = "write a KDE/Kate syntax definition, also read by pandoc"

    def generate(self, model: GrammarModel, out_dir: Path) -> list[Path]:
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"{self.language_name(model)}.xml"
        path.write_text(self.render(model), encoding="utf-8")
        return [path]

    # -- naming ------------------------------------------------------------

    def language_name(self, model: GrammarModel) -> str:
        """What the highlighted language is called.

        Taken from the file's own `> name(…)` when the grammar says so, and from
        the grammar file's name otherwise.
        """
        # The words of a file name come first, so `my-toy.mgff` gives `MyToy`
        # rather than a spelled-out hyphen.
        return setting(model.attributes, "name", None) or safe_identifier(
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
        name = self.language_name(model)
        attributes = {
            "name": name,
            "version": setting(model.attributes, "version", "1"),
            "kateversion": setting(model.attributes, "kateversion", KATE_VERSION),
            "section": setting(model.attributes, "section", "Sources"),
            "extensions": setting(model.attributes, "extensions", f"*.{name.lower()}"),
            "mimetype": setting(model.attributes, "mimetype", None),
            "author": setting(model.attributes, "author", None),
            "license": setting(model.attributes, "license", None),
            "priority": setting(model.attributes, "priority", None),
        }
        return Element(
            "language", {key: value for key, value in attributes.items() if value is not None}
        )

    def general_element(self, root: Element, model: GrammarModel) -> None:
        """The `<general>` block, which is where keyword matching is tuned.

        MGFF has no spelling for case-insensitive matching, so keywords are
        case-sensitive unless the grammar says otherwise.
        """
        general = root.child("general")
        general.child(
            "keywords",
            casesensitive=setting(model.attributes, "casesensitive", "1"),
            weakDeliminator=setting(model.attributes, "weakDeliminator", None),
            additionalDeliminator=setting(model.attributes, "additionalDeliminator", None),
        )
