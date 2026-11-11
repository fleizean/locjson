"""The built-in CLDR cardinal plural rules.

Each rule is a plain Python function over
:class:`~locjson.plural.operands.Operands`, written by hand from the CLDR rule
text it quotes. Nothing here parses rule strings or evaluates code.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import TYPE_CHECKING, Final, TypeAlias

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from locjson.plural.categories import PluralCategory
    from locjson.plural.operands import Operands

__all__ = ["BUILTIN_RULES", "CLDR_VERSION", "FALLBACK_RULE", "PluralRule", "RuleSpec"]

CLDR_VERSION: Final = "49"
"""The CLDR release the built-in rules follow."""

PluralRule: TypeAlias = "Callable[[Operands], str]"
"""A function from the operands of a count to a CLDR plural category name."""

RuleSpec: TypeAlias = "tuple[PluralRule, frozenset[str]]"
"""A rule and the set of categories it can return."""


def _one_i1_v0(op: Operands) -> PluralCategory:
    """CLDR 49 ``one: i = 1 and v = 0``; everything else is ``other``."""
    return "one" if op.i == 1 and op.v == 0 else "other"


def _east_slavic(op: Operands) -> PluralCategory:
    """CLDR 49 rule for ru and uk.

    * ``one: v = 0 and i % 10 = 1 and i % 100 != 11``
    * ``few: v = 0 and i % 10 = 2..4 and i % 100 != 12..14``
    * ``many: v = 0 and i % 10 = 0 or v = 0 and i % 10 = 5..9
      or v = 0 and i % 100 = 11..14``
    * ``other``: everything else (every count with fraction digits)
    """
    if op.v != 0:
        return "other"
    i10 = op.i % 10
    i100 = op.i % 100
    if i10 == 1 and i100 != 11:  # noqa: PLR2004
        return "one"
    if 2 <= i10 <= 4 and not 12 <= i100 <= 14:  # noqa: PLR2004
        return "few"
    return "many"


_ONE_OTHER: Final = frozenset({"one", "other"})
_ONE_FEW_MANY_OTHER: Final = frozenset({"one", "few", "many", "other"})

FALLBACK_RULE: Final[RuleSpec] = (_one_i1_v0, _ONE_OTHER)
"""The rule for languages without a built-in rule: ``one`` iff ``i = 1 and v = 0``."""

BUILTIN_RULES: Final[Mapping[str, RuleSpec]] = MappingProxyType(
    {
        "en": FALLBACK_RULE,
        "ru": (_east_slavic, _ONE_FEW_MANY_OTHER),
        "uk": (_east_slavic, _ONE_FEW_MANY_OTHER),
    }
)
"""Rule and categories by canonical locale tag (read-only)."""
