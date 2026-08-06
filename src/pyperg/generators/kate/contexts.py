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

**The phases before the last keep two jobs**: the expression each of their
matches recognises, and the order they are tried in where a context holds
several. A grammar of a single phase is a machine of one context, built straight
from that order — which is what `Tokens` is.

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

from ...mgff.common.rules import Reference
from ...mgff.semantics.model import GrammarModel, Production, Target
from ..utils.styles import styles_of
from ..utils.highlight import token_order
from ..utils.machine import POP
from ..utils.machine import Context as MachineContext
from ..utils.machine import ContextRule as MachineRule
from ..utils.machine import MachineBuilder
from ..utils.pipeline import productions_of, resolve_over, stages_of
from ..utils.walk import literal_of
from ..utils.xmlwrite import Element
from .rules import RuleBuilder, RuleContext
from .styles import FALLBACK_STYLE, style_for

#: The one context a grammar of a single phase amounts to. A grammar of more
#: names its contexts after the productions they came from.
TOKENS_CONTEXT = "Tokens"


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
        #: The phases, first to last. A terminal of a phase reading a list of
        #: earlier matches is rewritten as a call on the match it names, which
        #: has to happen before anything reads a rule tree.
        self.stages = stages_of(model)
        for stage in self.stages:
            resolve_over(stage)
        self.last = self.stages[-1]
        #: The phase whose order decides which match wins where several could.
        self.before = self.last.previous

        self.item_datas = ItemDatas()
        self.contexts: list[Element] = []
        #: The expressions of the phase before the last, which a grammar of a
        #: single phase uses on its own.
        self.before_rules = RuleBuilder(
            (self.before or self.last).target.productions
        )
        #: The rules of the machine's contexts, which reach across every phase.
        self.machine_rules = RuleBuilder(productions_of(self.stages))

    # -- the whole set -----------------------------------------------------

    def build(self) -> None:
        """Build every context, in the order Kate should read them.

        The first context listed is the one a document starts in. A grammar of
        several phases is spelled from the machine `utils.machine` derives, so
        every context holds what its place in the grammar reaches and nothing
        else. A grammar of one phase is a machine of a single context, and is
        built straight from that phase's order.
        """
        if self.before is not None:
            self.build_machine()
        else:
            self.build_tokens_context(self.last.target)

    # -- the machine -------------------------------------------------------

    def build_machine(self) -> None:
        """Spell every context of the machine derived from the last phase."""
        assert self.before is not None
        machine = MachineBuilder(
            self.last.target, token_order(self.before.target)
        ).build()
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
        lists = self.before_rules.list_elements() + self.machine_rules.list_elements()
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

    # -- a grammar of one phase ---------------------------------------------

    def build_tokens_context(self, target: Target) -> None:
        """One context holding a rule for every match `File` names."""
        element = self.context(TOKENS_CONTEXT)
        for name in token_order(target):
            production = target.productions[name]
            where = RuleContext(attribute=self.item_datas.attribute_for(production))
            element.children.extend(self.before_rules.rules_for(production, where))

    # -- Parse -------------------------------------------------------------

