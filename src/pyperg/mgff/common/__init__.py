"""The vocabulary a rule-tree backend starts with.

MGFF itself defines no shapes: a grammar is lines, scopes and macro definitions,
and nothing in Parts 1 and 2 says that `( R )+` repeats anything. What makes it
repeat is the ordered list of macros a generator reads items through, and that
list is common to every backend rather than particular to one.

## Where to find a shape

One file per family of construct, each holding the shape, what a call of it
carries, and what it produces — so a shape and its meaning are never apart:

| Written as        | Shape                 | Macro           | File            |
| ----------------- | --------------------- | --------------- | --------------- |
| `( … )`           | `SUBGROUP_SHAPE`      | `SUBGROUP`      | `grouping.py`   |
| `( R )+ * ?`      | `REPETITION_SHAPE`    | `REPETITION`    | `grouping.py`   |
| `(A)\\|(B)`, `(A)/(B)` | `CHOICE_SHAPE`   | `CHOICE`        | `grouping.py`   |
| `a-z\\|A-Z`        | `CHARACTER_SET_SHAPE` | `CHARACTER_SET` | `characters.py` |
| `a`, `Letter`     | `CHARACTER_SHAPE`     | `CHARACTER`     | `characters.py` |
| `Digit`           | `NAME`                | consults a scope | `order.py`     |
| `sep(x)by(y)`     | `NAME_WITH_ARGUMENTS` | consults a scope | `order.py`     |

## The rest

    order.py       the list itself, and where a backend's own macros go in it
    charset.py     what a character set is: its parts, and reading text as one
    categories.py  the Unicode category names a part may use

`charset` and `categories` are plain helpers — no shape, no macro, no dependency
on anything else here — so they can be read on their own.
"""

from .characters import (
    CHARACTER,
    CHARACTER_MACROS,
    CHARACTER_SET,
    CHARACTER_SET_SHAPE,
    CHARACTER_SHAPE,
    character_set_matched_by,
)
from .charset import (
    CharacterSet,
    CharacterSetPart,
    parse_character_set,
    parse_character_set_part,
)
from .categories import categories_covered_by, is_category_name
from .grouping import (
    CHOICE,
    CHOICE_SHAPE,
    REPETITION,
    REPETITION_SHAPE,
    SUBGROUP,
    SUBGROUP_SHAPE,
)
from .order import NAME, NAME_WITH_ARGUMENTS, rule_tree_macro_order

__all__ = [
    "CHARACTER",
    "CHARACTER_MACROS",
    "CHARACTER_SET",
    "CHARACTER_SET_SHAPE",
    "CHARACTER_SHAPE",
    "CHOICE",
    "CHOICE_SHAPE",
    "NAME",
    "NAME_WITH_ARGUMENTS",
    "REPETITION",
    "REPETITION_SHAPE",
    "SUBGROUP",
    "SUBGROUP_SHAPE",
    "CharacterSetPart",
    "CharacterSet",
    "categories_covered_by",
    "character_set_matched_by",
    "is_category_name",
    "parse_character_set",
    "parse_character_set_part",
    "rule_tree_macro_order",
]
