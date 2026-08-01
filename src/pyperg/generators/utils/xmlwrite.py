"""A small XML element builder.

`xml.etree` could write these documents, but it reorders nothing and escapes
little, and a syntax definition is read by people as often as by programs. This
builder keeps attributes in the order they were given and writes an empty
element as `<tag/>`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .emit import Emitter

#: The five characters XML reserves, and their entities.
ENTITIES = {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&apos;"}


def escape_text(text: str) -> str:
    """Escape character data."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def escape_attribute(text: str) -> str:
    """Escape an attribute value, which is written in double quotes.

    A tab or a newline inside an attribute would otherwise be folded to a space
    by a conforming parser, so both are written as character references.
    """
    out = []
    for char in text:
        if char in ENTITIES:
            out.append(ENTITIES[char])
        elif char in "\n\r\t":
            out.append(f"&#{ord(char)};")
        else:
            out.append(char)
    return "".join(out)


@dataclass(slots=True)
class Element:
    """One element: a tag, its attributes in order, and its children or text."""

    tag: str
    attributes: dict[str, str] = field(default_factory=dict)
    children: list["Element"] = field(default_factory=list)
    text: str | None = None

    def child(self, tag: str, **attributes: str | None) -> "Element":
        """Append a child element and return it.

        An attribute given as None is left out, which is how an optional
        attribute is written without a conditional at every call site.
        """
        element = Element(
            tag, {key: value for key, value in attributes.items() if value is not None}
        )
        self.children.append(element)
        return element

    def leaf(self, tag: str, text: str, **attributes: str | None) -> "Element":
        """Append a child holding text and return this element, for chaining."""
        element = self.child(tag, **attributes)
        element.text = text
        return self

    def write(self, out: Emitter) -> None:
        """Write the element and everything below it."""
        rendered = "".join(
            f' {key}="{escape_attribute(value)}"' for key, value in self.attributes.items()
        )
        if self.text is not None:
            out.line(f"<{self.tag}{rendered}>{escape_text(self.text)}</{self.tag}>")
        elif not self.children:
            out.line(f"<{self.tag}{rendered}/>")
        else:
            out.line(f"<{self.tag}{rendered}>")
            with out.nested():
                for child in self.children:
                    child.write(out)
            out.line(f"</{self.tag}>")

    def render(self, indent: str = "  ") -> str:
        """The element as text, with no XML declaration in front."""
        out = Emitter(indent)
        self.write(out)
        return out.render()
