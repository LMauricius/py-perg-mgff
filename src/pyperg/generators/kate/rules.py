"""Choosing the best Kate rule for a piece of a grammar.

Kate offers a dozen ways to match text and tries the rules of a context in order
at every position, so the choice matters: `DetectChar` compares one character,
while `RegExpr` runs an expression engine. The table below is walked top to
bottom and the first row that fits wins, which puts the cheap rules first and
leaves `RegExpr` as the fallback.

    DetectSpaces   a run of whitespace
    DetectChar     one fixed character
    Detect2Chars   two fixed characters
    WordDetect     a fixed word, matched only between word boundaries
    StringDetect   any other fixed string
    AnyChar        one character out of a handful of fixed ones
    keyword        a choice of fixed words, kept in a `<list>`
    RegExpr        anything else that has a regular form

`RangeDetect` is deliberately absent. It matches everything between a fixed
opening and closing character, which is wider than any grammar that spells out
what may appear between them, and quietly widening a rule is worse than paying
for an expression.

The literal rows depend on **fusing**: MGFF spells a two-character token as two
items, so `< =` is two single-character nodes until `utils.walk.merge_adjacent_literals`
merges them. Everything from `DetectChar` to `StringDetect` is unreachable
without that step.
"""

from __future__ import annotations

from dataclasses import dataclass

from ...diagnostics.errors import GeneratorError
from ...mgff.common.characters import character_set_matched_by
from ...mgff.common.rules import Rule, Repetition, Sequence
from ...mgff.systems.model import Production
from ..utils.naming import NameAllocator, safe_identifier
from ..utils.regex import regex_of
from ..utils.walk import top_level_parts, merge_adjacent_literals, literal_of
from ..utils.words import is_word, is_word_bounded
from ..utils.xmlwrite import Element

#: The whitespace a `DetectSpaces` rule stands for.
WHITESPACE = set(" \t\n\r\f\v")


def _is_xml_character(char: str) -> bool:
    """Whether one character may appear in an XML 1.0 document at all."""
    code = ord(char)
    return (
        char in "\t\n\r"
        or 0x20 <= code <= 0xD7FF
        or 0xE000 <= code <= 0xFFFD
        or 0x10000 <= code <= 0x10FFFF
    )


def is_xml_text(text: str) -> bool:
    """Whether a fixed string can be written into a syntax definition.

    XML 1.0 carries tab, line feed and carriage return and nothing else below
    U+0020 — not even as a character reference — so a literal holding a control
    character cannot go into a rule's attribute at all. Such a match is left to
    `RegExpr`, whose `\\x{00}` spelling is well-formed.
    """
    return all(_is_xml_character(char) for char in text)


@dataclass(slots=True)
class RuleContext:
    """What a rule does besides matching: its style and where it goes next."""

    attribute: str
    context: str | None = None  # a context name, `#stay`, `#pop`, …
    begin_region: str | None = None
    end_region: str | None = None
    look_ahead: bool = False

    def rule_element(self, tag: str, **attributes: str | None) -> Element:
        """Build the rule element, with the shared attributes filled in."""
        return Element(
            tag,
            {
                key: value
                for key, value in {
                    **attributes,
                    "attribute": self.attribute,
                    "context": self.context,
                    "beginRegion": self.begin_region,
                    "endRegion": self.end_region,
                    "lookAhead": "1" if self.look_ahead else None,
                }.items()
                if value is not None
            },
        )


class RuleBuilder:
    """Turns rule trees into Kate rules, collecting the keyword lists it needs."""

    def __init__(self, productions: dict[str, Production]) -> None:
        self.productions = productions
        #: Generated `<list>` elements, by name, in the order they were made.
        self.lists: dict[str, list[str]] = {}
        self.list_names = NameAllocator()

    def find_production(self, name: str) -> Production | None:
        """Find a production of the target being generated."""
        return self.productions.get(name)

    # -- whole productions -------------------------------------------------

    def rules_for_production(
        self, production: Production, rule_context: RuleContext
    ) -> list[Element]:
        """Every rule a production needs, one per alternative.

        Several cheap rules beat one expression, so the alternatives are not
        merged unless they make a keyword list between them. A length-based
        choice is ordered longest first, since Kate takes the first rule that
        matches and MGFF wants the longest.
        """
        alternatives = list(production.alternatives)
        if not alternatives:
            raise GeneratorError(f"production {production.name!r} matches nothing")

        keywords = self.keyword_rule(alternatives, rule_context, production.name)
        if keywords is not None:
            return [keywords]

        if production.choice_symbol == "|":
            alternatives.sort(key=_literal_length_of, reverse=True)
        return [
            self.cheapest_rule_for(alternative, rule_context)
            for alternative in alternatives
        ]

    def keyword_rule(
        self, alternatives: list[Rule], rule_context: RuleContext, name: str
    ) -> Element | None:
        """One `keyword` rule for a choice of plain words, or None.

        Kate matches a keyword list by hashed lookup, so this is the fastest
        thing a long list of alternatives can become.
        """
        if len(alternatives) < 2:
            return None
        words = [literal_of(alternative) for alternative in alternatives]
        if not all(word is not None and is_word(word) for word in words):
            return None
        if not all(is_xml_text(word) for word in words if word is not None):
            return None
        # Keyed by the production, so a list reached from several contexts is
        # written once and named the same everywhere.
        list_name = self.list_names.allocate(safe_identifier(name).lower(), key=name)
        self.lists.setdefault(list_name, [word for word in words if word is not None])
        return rule_context.rule_element("keyword", String=list_name)

    # -- single rules ------------------------------------------------------

    def cheapest_rule_for(self, node: Rule, rule_context: RuleContext) -> Element:
        """The cheapest Kate rule matching a rule tree.

        Raises `GeneratorError` when the tree has no regular form, which for
        Kate means a production that reaches itself.
        """
        fused = _with_literals_merged(node)

        for attempt in (self.spaces_rule, self.literal_rule, self.any_char_rule):
            rule = attempt(fused, rule_context)
            if rule is not None:
                return rule

        pattern = regex_of(fused, self.find_production)
        if pattern is None:
            raise GeneratorError(
                "a rule that reaches itself cannot be matched by a single Kate rule; "
                "Kate matches text with expressions, which cannot recurse"
            )
        return rule_context.rule_element("RegExpr", String=pattern)

    def spaces_rule(self, node: Rule, rule_context: RuleContext) -> Element | None:
        """`DetectSpaces` for a run of whitespace of any length."""
        if not isinstance(node, Repetition) or node.minimum > 1:
            return None
        characters = character_set_matched_by(node.body)
        if characters is None:
            return None
        if not all(
            part.kind == "character" and part.value in WHITESPACE
            for part in characters.parts
        ):
            return None
        return rule_context.rule_element("DetectSpaces")

    def literal_rule(self, node: Rule, rule_context: RuleContext) -> Element | None:
        """`DetectChar`, `Detect2Chars`, `WordDetect` or `StringDetect`."""
        literal = literal_of(node)
        if literal is None or not literal:
            return None
        # A literal XML cannot carry is matched by an expression instead, which
        # spells a control character as `\x{00}`.
        if not is_xml_text(literal):
            return None
        if len(literal) == 1:
            return rule_context.rule_element("DetectChar", char=literal)
        if len(literal) == 2:
            return rule_context.rule_element(
                "Detect2Chars", char=literal[0], char1=literal[1]
            )
        tag = "WordDetect" if is_word_bounded(literal) else "StringDetect"
        return rule_context.rule_element(tag, String=literal)

    def any_char_rule(self, node: Rule, rule_context: RuleContext) -> Element | None:
        """`AnyChar` for one character out of a fixed handful."""
        characters = character_set_matched_by(node)
        if characters is None:
            return None
        parts = characters.parts
        if len(parts) < 2 or not all(part.kind == "character" for part in parts):
            return None
        listed = "".join(part.value for part in parts)
        if not is_xml_text(listed):
            return None
        return rule_context.rule_element("AnyChar", String=listed)

    # -- keyword lists -----------------------------------------------------

    def list_elements(self) -> list[Element]:
        """The `<list>` elements the rules built so far refer to."""
        elements = []
        for name, words in self.lists.items():
            element = Element("list", {"name": name})
            for word in words:
                element.text_child("item", word)
            elements.append(element)
        return elements


def _with_literals_merged(node: Rule) -> Rule:
    """Merge the single-character runs of a node, so literals become strings."""
    parts = top_level_parts(node)
    if len(parts) < 2:
        return node
    fused = merge_adjacent_literals(parts)
    return fused[0] if len(fused) == 1 else Sequence(fused)


def _literal_length_of(node: Rule) -> int:
    """How long the fixed string a node matches is, or -1 when it is not fixed."""
    literal = literal_of(_with_literals_merged(node))
    return len(literal) if literal is not None else -1
