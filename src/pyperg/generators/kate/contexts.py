"""Spelling the highlighting machine as Kate's contexts.

Kate highlights with a stack of **contexts**. A context is an ordered list of
rules; at every position the first rule that matches wins, and a rule may push
another context, pop back, or stay. `utils.machine` derives that machine from a
grammar's `Parse` target, and this module writes it down:

    Machine                Kate
    ----------------------------------------------------
    Context                <context>
    Context.styles         attribute=, the style its text takes
    Context.line_end       lineEndContext=
    ContextRule.push       context="Name"
    ContextRule.pop n      context="#pop" repeated n times
    ContextRule.region     beginRegion / endRegion, which is what folds
    Match.look_ahead       lookAhead="1"
    Match.word_boundary    WordDetect, which matches between deliminators

**A context holds what its place in the grammar reaches, and nothing else**, so
`d` is a keyword where a line may open with one and ordinary text inside a
subgroup, and a comment stays a comment across the lines its group spans.

**`Lex` keeps two jobs**: the expression each token matches with, and the order
tokens are tried in where a context holds several. A grammar with no `Parse`
target is a machine of a single context, and is built straight from that order —
which is what `Tokens` is.

A production reached as a plain call is spelled from the whole production rather
than from one expression, so a choice of fixed words still becomes a hashed
`<list>` and still matches only between word boundaries.

```mermaid
stateDiagram-v2
    [*] --> File
    File --> Definition: <code>d</code> pushes
    Definition --> DefinitionLine: line end
    DefinitionLine --> AltLine: <code>|</code> pushes
    DefinitionLine --> [*]: any other line pops the chain
    File --> CommentLine: <code>#</code> pushes
    CommentLine --> CommentGroup: <code>(</code> pushes
    CommentLine --> [*]: line end
```
"""

from __future__ import annotations

import sys

from ...diagnostics.errors import GeneratorError
from ...mgff.common.rules import Reference
from ...mgff.semantics.model import GrammarModel, Production, Target
from ..utils.styles import styles_of
from ..utils.highlight import token_order
from ..utils.machine import POP
from ..utils.machine import Context as MachineContext
from ..utils.machine import ContextRule as MachineRule
from ..utils.machine import MachineBuilder
from ..utils.walk import literal_of
from ..utils.xmlwrite import Element
from .rules import RuleBuilder, RuleContext
from .styles import FALLBACK_STYLE, style_for

#: The one context a grammar of tokens alone amounts to. A grammar with a
#: `Parse` target names its contexts after the productions they came from.
TOKENS_CONTEXT = "Tokens"

#: The targets the backend understands.
LEX_TARGET = "Lex"
PARSE_TARGET = "Parse"


# -- styles ----------------------------------------------------------------


class ItemDatas:
    """The styles the generated file declares, in the order they were needed."""

    def __init__(self) -> None:
        self.styles: dict[str, str] = {FALLBACK_STYLE: f"ds{FALLBACK_STYLE}"}

    def attribute_for(self, production: Production) -> str:
        """Register a production's style and return the itemData's name."""
        return self.for_styles(styles_of(production))

    def for_styles(self, styles: list[str]) -> str:
        """Register a set of styles and return the itemData's name."""
        name, default_style = style_for(styles or [FALLBACK_STYLE])
        self.styles.setdefault(name, default_style)
        return name

    def elements(self) -> list[Element]:
        """The `<itemData>` elements, one per style."""
        return [
            Element("itemData", {"name": name, "defStyleNum": default_style})
            for name, default_style in self.styles.items()
        ]


# -- reading the targets ---------------------------------------------------


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
        #: The rules of the machine's contexts, which reach across both targets.
        self.machine_rules = RuleBuilder(
            {**(self.lex.productions if self.lex else {}),
             **(self.parse.productions if self.parse else {})}
        )
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

        The first context listed is the one a document starts in. A grammar with
        a `Parse` target is spelled from the machine `utils.machine` derives, so
        every context holds what its place in the grammar reaches and nothing
        else. One with only tokens is a machine of a single context, and is
        built straight from the `Lex` order.
        """
        if self.parse is not None:
            self.build_machine()
        elif self.lex is not None:
            self.build_tokens_context(self.lex)

    # -- the machine -------------------------------------------------------

    def build_machine(self) -> None:
        """Spell every context of the machine derived from `Parse`."""
        assert self.parse is not None
        order = token_order(self.lex) if self.lex is not None else []
        machine = MachineBuilder(self.parse, order).build()
        # The context a document starts in comes first, which is how Kate reads
        # a definition: the first context listed is the initial one.
        for name in [machine.start, *machine.contexts]:
            context = machine.contexts.get(name)
            if context is not None and not any(
                element.attributes.get("name") == name for element in self.contexts
            ):
                self.build_context(context)

    def build_context(self, context: MachineContext) -> None:
        """One context of the machine, with its rules in the order they are tried."""
        element = self.context(
            context.name,
            attribute=self.item_datas.for_styles(context.styles),
            lineEndContext=context.line_end,
        )
        for rule in context.rules:
            element.children.extend(self.build_rule(rule))

    def build_rule(self, rule: MachineRule) -> list[Element]:
        """One rule of the machine as the Kate rules that spell it.

        `#pop` repeated is how Kate spells leaving several contexts at once,
        which is what a chained line context does when its line is not one of
        its own.

        A rule that is nothing but a call is spelled from the whole production,
        so a choice of fixed words still becomes a `<list>` and still matches
        only between word boundaries — the `Lu` of `Lucky` is not a category.
        Anything else is one expression.
        """
        where = RuleContext(
            attribute=self.item_datas.for_styles(rule.styles),
            context=rule.push or (POP * rule.pop if rule.pop else None),
            begin_region=rule.region if rule.push else None,
            end_region=rule.region if rule.pop and not rule.push else None,
            look_ahead=rule.match.look_ahead,
        )
        if rule.match.word_boundary:
            # `WordDetect` matches only between deliminators, which is what
            # keeps the `d` of `Digit` from opening a definition.
            literal = literal_of(rule.match.rule)
            if literal:
                return [where.applied_to("WordDetect", String=literal)]
        called = self.called_production(rule)
        if called is not None:
            return self.machine_rules.rules_for(called, where)
        return [self.machine_rules.rule_for(rule.match.rule, where)]

    def called_production(self, rule: MachineRule) -> Production | None:
        """The production a plain match rule calls, when that is all it does."""
        if rule.push or rule.pop or rule.match.look_ahead:
            return None
        if isinstance(rule.match.rule, Reference):
            return self.machine_rules.lookup(rule.match.rule.name)
        return None

    def elements(self) -> tuple[list[Element], list[Element], list[Element]]:
        """The contexts, the item data and the keyword lists."""
        lists = self.lex_rules.list_elements() + self.machine_rules.list_elements()
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

