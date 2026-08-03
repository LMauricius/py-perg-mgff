"""Building Kate's contexts from the `Lex` and `Parse` targets.

Kate highlights with a stack of **contexts**. A context is an ordered list of
rules; at every position the first rule that matches wins, and a rule may push
another context, pop back, or stay. That is a pushdown machine over text, so it
reads nesting but it does not parse: there is no backtracking, and a rule cannot
recurse.

Both targets start at a macro named `File`.

**`Lex`** maps exactly. `File` lists the token productions, in the order Kate
should try them, and each becomes one or more rules in the `Tokens` context.
Only the productions `File` names become rules; the rest are helpers, inlined
into the expressions that use them, so nothing is tried that the grammar did not
ask for.

**`Parse`** maps approximately, and the shape of the approximation is this: what
Kate can genuinely reproduce from a grammar is *nesting*, so a production that
brackets something — an alternative opening and closing with a fixed character —
becomes a context of its own, pushed by the opening character and popped by the
closing one, and marked as a foldable region. Everything else contributes its
terminals. The result highlights and folds correctly; it does not reject input
the grammar would reject.

    File     the initial context; nothing but an entry point
    Grammar  what may appear anywhere: nesting, then tokens, then loose terminals
    Tokens   the `Lex` rules
    <P>      one per bracketing `Parse` production

```mermaid
stateDiagram-v2
    [*] --> File
    File --> Grammar: include
    Grammar --> Tokens: include
    Grammar --> Factor: ( pushes
    Factor --> Grammar: include
    Factor --> [*]: ) pops
```
"""

from __future__ import annotations

import sys

from ...diagnostics.errors import GeneratorError
from ...mgff.semantics.model import GrammarModel, Production, Target
from ..utils.classes import classes_of
from ..utils.highlight import (
    START_PRODUCTION,
    brackets_of,
    reachable_productions,
    token_order,
)
from ..utils.walk import flatten, fuse_literals, single_character
from ..utils.xmlwrite import Element
from .rules import RuleBuilder, RuleContext
from .styles import FALLBACK_STYLE, style_for

#: The names of the contexts this backend always builds. The initial one is
#: named after the macro a target starts at, since that is what it stands for.
FILE_CONTEXT = START_PRODUCTION
GRAMMAR_CONTEXT = "Grammar"
TOKENS_CONTEXT = "Tokens"

#: The targets the backend understands.
LEX_TARGET = "Lex"
PARSE_TARGET = "Parse"


# -- token classes ---------------------------------------------------------


class ItemDatas:
    """The styles the generated file declares, in the order they were needed."""

    def __init__(self) -> None:
        self.styles: dict[str, str] = {FALLBACK_STYLE: f"ds{FALLBACK_STYLE}"}

    def attribute_for(self, production: Production) -> str:
        """Register a production's style and return the itemData's name."""
        name, default_style = style_for(classes_of(production))
        self.styles.setdefault(name, default_style)
        return name

    def elements(self) -> list[Element]:
        """The `<itemData>` elements, one per style."""
        return [
            Element("itemData", {"name": name, "defStyleNum": default_style})
            for name, default_style in self.styles.items()
        ]


# -- reading the targets ---------------------------------------------------


def loose_terminals(productions: list[Production]) -> list[str]:
    """The fixed single characters a target's rules mention, deduplicated.

    These are the operators and separators a `Parse` grammar writes inline. They
    go last, so a token of the same shape is matched as that token first.
    """
    found: list[str] = []
    for production in productions:
        for alternative in production.alternatives:
            for part in fuse_literals(flatten(alternative)):
                char = single_character(part)
                if char is not None and char not in found and not char.isspace():
                    found.append(char)
    return found


# -- building --------------------------------------------------------------


class ContextBuilder:
    """Turns a resolved grammar into Kate's contexts, item data and lists."""

    def __init__(self, model: GrammarModel) -> None:
        self.model = model
        self.lex = model.target(LEX_TARGET)
        self.parse = model.target(PARSE_TARGET)
        self.item_datas = ItemDatas()
        self.contexts: list[Element] = []
        self.lex_rules = RuleBuilder(self.lex.productions if self.lex else {})
        self.parse_rules = RuleBuilder(self.parse.productions if self.parse else {})
        self._bracketing: list[tuple[Production, tuple[str, str]]] | None = None
        if self.lex is None and self.parse is None:
            raise GeneratorError(
                "the grammar has no `Lex` or `Parse` target; the Kate backend "
                "generates from those two"
            )
        self._warn_about_other_targets()

    def _warn_about_other_targets(self) -> None:
        """Say which targets are being ignored, rather than dropping them silently."""
        for target in self.model.targets:
            if target.name not in (LEX_TARGET, PARSE_TARGET):
                print(
                    f"pyperg: kate: target {target.name!r} is not generated; "
                    f"this backend reads {LEX_TARGET} and {PARSE_TARGET}.",
                    file=sys.stderr,
                )

    # -- the whole set -----------------------------------------------------

    def build(self) -> None:
        """Build every context, in the order Kate should read them.

        The first context listed is the one a document starts in.
        """
        if self.parse is not None:
            self.build_file_context()
            self.build_grammar_context()
            self.build_bracket_contexts()
        if self.lex is not None:
            self.build_tokens_context(self.lex)

    def elements(self) -> tuple[list[Element], list[Element], list[Element]]:
        """The contexts, the item data and the keyword lists."""
        lists = self.lex_rules.list_elements() + self.parse_rules.list_elements()
        return self.contexts, self.item_datas.elements(), lists

    def context(self, name: str, **attributes: str | None) -> Element:
        """Start a context, filling in the attributes every one of ours carries."""
        element = Element(
            "context",
            {
                "name": name,
                "attribute": FALLBACK_STYLE,
                "lineEndContext": "#stay",
                **{key: value for key, value in attributes.items() if value is not None},
            },
        )
        self.contexts.append(element)
        return element

    # -- Lex ---------------------------------------------------------------

    def build_tokens_context(self, lex: Target) -> None:
        """One context holding a rule for every token `File` names."""
        element = self.context(TOKENS_CONTEXT)
        for name in token_order(lex):
            production = lex.productions[name]
            where = RuleContext(attribute=self.item_datas.attribute_for(production))
            element.children.extend(self.lex_rules.rules_for(production, where))

    # -- Parse -------------------------------------------------------------

    def parse_productions(self) -> list[Production]:
        """The `Parse` productions reachable from its `File`, `File` aside.

        A production of the `Lex` target reached from here is left out: its
        tokens are already matched by the `Tokens` context. Empty when the
        grammar has no `Parse` target at all.
        """
        if self.parse is None:
            return []
        return reachable_productions(self.parse)

    def build_file_context(self) -> None:
        """The initial context: an entry point onto everything else."""
        element = self.context(FILE_CONTEXT)
        element.child("IncludeRules", context=GRAMMAR_CONTEXT)

    def build_grammar_context(self) -> None:
        """What may appear anywhere: nesting first, then tokens, then terminals.

        The order is what makes the approximation behave: a bracket opens its
        own context before a token rule of the same shape can swallow it, and a
        loose terminal is only reached when nothing better matched.
        """
        element = self.context(GRAMMAR_CONTEXT)
        bracketing = self.bracketing_productions()

        for production, (opening, _) in bracketing:
            where = RuleContext(
                attribute=self.item_datas.attribute_for(production),
                context=production.name,
                begin_region=production.name,
            )
            element.children.append(where.applied_to("DetectChar", char=opening))

        if self.lex is not None:
            element.child("IncludeRules", context=TOKENS_CONTEXT)

        bracket_characters = {char for _, pair in bracketing for char in pair}
        plain = RuleContext(attribute=FALLBACK_STYLE)
        for char in loose_terminals(self.parse_productions()):
            if char not in bracket_characters:
                element.children.append(plain.applied_to("DetectChar", char=char))

    def build_bracket_contexts(self) -> None:
        """One context per bracketing production, popped by its closing character."""
        for production, (_, closing) in self.bracketing_productions():
            element = self.context(production.name)
            where = RuleContext(
                attribute=self.item_datas.attribute_for(production),
                context="#pop",
                end_region=production.name,
            )
            element.children.append(where.applied_to("DetectChar", char=closing))
            element.child("IncludeRules", context=GRAMMAR_CONTEXT)

    def bracketing_productions(self) -> list[tuple[Production, tuple[str, str]]]:
        """Every `Parse` production that wraps something in a fixed pair.

        Computed once and cached: the grammar context and the bracket contexts
        must agree on which productions these are.
        """
        if self._bracketing is None:
            self._bracketing = [
                (production, pair)
                for production in self.parse_productions()
                if (pair := brackets_of(production)) is not None
            ]
        return self._bracketing
