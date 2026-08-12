"""Where a match goes: the fields and lists a production writes itself into.

A grammar that only recognises text has nothing to say here. One that produces
something — a parse tree, a token list, a stream of anything — needs to say
*where* each match ends up, and MGFF says it with two attributes on the match
itself rather than at the place it is used:

    d Condition = Expression
                > store(condition)

    d Keyword = i f / e l s e
              > class(Keyword) push(tokens)

`store(field)` assigns the match to one field of whatever called it; `push(list)`
appends it to a named list. The two are the same idea for a field that holds one
thing and a field that holds many. Storing the same field twice from one caller
is not allowed; pushing is the way to say "again".

Keeping the name on the rule rather than on the call site means a production is
written once and read the same way everywhere, and everything about a match — its
class, its style, where it goes — is in one attribute list. It also means a
production used in two places writes to the same field in both, which is usually
what was meant and is otherwise a sign the two uses want two productions.
"""

from __future__ import annotations

import re

from ...diagnostics.errors import GeneratorError
from ...mgff.systems.model import Production

#: What a field or a list may be called. Deliberately an identifier, since a
#: field name has to survive into whatever the backend generates.
VALID_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def _single_attribute_name(production: Production, attribute: str) -> str:
    """The single name one `store`/`push` argument list holds."""
    arguments = production.attributes[attribute]
    if len(arguments) != 1:
        raise GeneratorError(
            f"`{attribute}` on {production.name!r} takes one name, as in "
            f"`> {attribute}(tokens)`; this one has {len(arguments)}"
        )
    name = arguments[0]
    if not VALID_NAME.fullmatch(name):
        raise GeneratorError(
            f"{name!r} on {production.name!r} is no name for a field; a name is a "
            "letter or an underscore followed by letters, digits or underscores"
        )
    return name


def stored_field_of(production: Production) -> str | None:
    """The field a production's match is assigned to, or None when it is not."""
    if "store" not in production.attributes:
        return None
    return _single_attribute_name(production, "store")


def pushed_list_names_of(production: Production) -> list[str]:
    """The lists a production's match is appended to; empty when it is not.

    A production may name several, so one match can reach a token list and a
    channel of its own without being written twice.
    """
    if "push" not in production.attributes:
        return []
    arguments = production.attributes["push"]
    if not arguments:
        raise GeneratorError(
            f"`push` on {production.name!r} needs a list, as in `> push(tokens)`"
        )
    return [_checked_list_name(production, name) for name in arguments]


def _checked_list_name(production: Production, name: str) -> str:
    """One list name of a `push`, checked the way a field name is."""
    if not VALID_NAME.fullmatch(name):
        raise GeneratorError(
            f"{name!r} on {production.name!r} is no name for a list; a name is a "
            "letter or an underscore followed by letters, digits or underscores"
        )
    return name
