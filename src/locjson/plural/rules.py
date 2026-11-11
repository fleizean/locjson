"""The built-in CLDR cardinal plural rules.

Each rule is a plain Python function over
:class:`~locjson.plural.operands.Operands`, written by hand from the CLDR rule
text it quotes. Nothing here parses rule strings or evaluates code.

Source: ``cldr-json`` tag 49.0.0, ``cldr-core/supplemental/plurals.json``
(cardinal rules) and ``parentLocales.json`` (the locales whose parent is
``pt-PT``). ``scripts/extract_cldr_plural_samples.py`` extracts the same rule
text and CLDR's sample numbers into ``tests/data/cldr49_plural_samples.json``,
and the tests check every sample against these functions.

Conventions, from Unicode TR35 "Language Plural Rules":

* The compact-exponent operands ``c`` and ``e`` are always 0 in locjson, so a
  condition such as ``e = 0 and X or e != 0..5`` reduces to ``X``.
* A condition on ``n`` with an integer value or range (``n = 1``,
  ``n % 100 = 3..10``) only holds for an integral ``n``. It is written as
  ``f == 0`` plus the same condition on ``i``.
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

_MILLION: Final = 1_000_000


def _one_i1_v0(op: Operands) -> PluralCategory:
    """CLDR 49 for en, de, nl (and unknown languages).

    * ``one: i = 1 and v = 0``
    * ``other``: everything else
    """
    return "one" if op.i == 1 and op.v == 0 else "other"


def _one_n1(op: Operands) -> PluralCategory:
    """CLDR 49 for tr.

    * ``one: n = 1``
    * ``other``: everything else
    """
    return "one" if op.i == 1 and op.f == 0 else "other"


def _is_million_many(op: Operands) -> bool:
    # CLDR 49 many: e = 0 and i != 0 and i % 1000000 = 0 and v = 0 or e != 0..5
    return op.v == 0 and op.i != 0 and op.i % _MILLION == 0


def _es(op: Operands) -> PluralCategory:
    """CLDR 49 for es.

    * ``one: n = 1``
    * ``many: e = 0 and i != 0 and i % 1000000 = 0 and v = 0 or e != 0..5``
    * ``other``: everything else
    """
    if op.i == 1 and op.f == 0:
        return "one"
    return "many" if _is_million_many(op) else "other"


def _fr_pt(op: Operands) -> PluralCategory:
    """CLDR 49 for fr and pt.

    * ``one: i = 0..1``
    * ``many: e = 0 and i != 0 and i % 1000000 = 0 and v = 0 or e != 0..5``
    * ``other``: everything else
    """
    if op.i <= 1:
        return "one"
    return "many" if _is_million_many(op) else "other"


def _it_pt_pt(op: Operands) -> PluralCategory:
    """CLDR 49 for it and pt-PT (and the locales whose parent is pt-PT).

    * ``one: i = 1 and v = 0``
    * ``many: e = 0 and i != 0 and i % 1000000 = 0 and v = 0 or e != 0..5``
    * ``other``: everything else
    """
    if op.i == 1 and op.v == 0:
        return "one"
    return "many" if _is_million_many(op) else "other"


def _ru_uk(op: Operands) -> PluralCategory:
    """CLDR 49 for ru and uk.

    * ``one: v = 0 and i % 10 = 1 and i % 100 != 11``
    * ``few: v = 0 and i % 10 = 2..4 and i % 100 != 12..14``
    * ``many: v = 0 and i % 10 = 0 or v = 0 and i % 10 = 5..9
      or v = 0 and i % 100 = 11..14``
    * ``other``: everything else

    ``many`` covers every integer that is neither ``one`` nor ``few``, so
    only counts with fraction digits are ``other``.
    """
    if op.v != 0:
        return "other"
    i10 = op.i % 10
    i100 = op.i % 100
    if i10 == 1 and i100 != 11:
        return "one"
    if 2 <= i10 <= 4 and not 12 <= i100 <= 14:
        return "few"
    return "many"


def _pl(op: Operands) -> PluralCategory:
    """CLDR 49 for pl.

    * ``one: i = 1 and v = 0``
    * ``few: v = 0 and i % 10 = 2..4 and i % 100 != 12..14``
    * ``many: v = 0 and i != 1 and i % 10 = 0..1 or v = 0 and i % 10 = 5..9
      or v = 0 and i % 100 = 12..14``
    * ``other``: everything else

    ``many`` covers every integer that is neither ``one`` nor ``few``, so
    only counts with fraction digits are ``other``.
    """
    if op.v != 0:
        return "other"
    if op.i == 1:
        return "one"
    if 2 <= op.i % 10 <= 4 and not 12 <= op.i % 100 <= 14:
        return "few"
    return "many"


def _cs(op: Operands) -> PluralCategory:
    """CLDR 49 for cs.

    * ``one: i = 1 and v = 0``
    * ``few: i = 2..4 and v = 0``
    * ``many: v != 0``
    * ``other``: everything else
    """
    if op.v != 0:
        return "many"
    if op.i == 1:
        return "one"
    return "few" if 2 <= op.i <= 4 else "other"


def _ar(op: Operands) -> PluralCategory:
    """CLDR 49 for ar.

    * ``zero: n = 0``
    * ``one: n = 1``
    * ``two: n = 2``
    * ``few: n % 100 = 3..10``
    * ``many: n % 100 = 11..99``
    * ``other``: everything else
    """
    if op.f != 0:
        return "other"
    if op.i <= 2:
        return ("zero", "one", "two")[op.i]
    i100 = op.i % 100
    if 3 <= i100 <= 10:
        return "few"
    return "many" if i100 >= 11 else "other"


def _he(op: Operands) -> PluralCategory:
    """CLDR 49 for he (there is no ``many`` form).

    * ``one: i = 1 and v = 0 or i = 0 and v != 0``
    * ``two: i = 2 and v = 0``
    * ``other``: everything else
    """
    if op.v == 0:
        if op.i == 1:
            return "one"
        return "two" if op.i == 2 else "other"
    return "one" if op.i == 0 else "other"


def _other(op: Operands) -> PluralCategory:  # noqa: ARG001
    """CLDR 49 for ja, zh and ko: every count is ``other``."""
    return "other"


_OTHER: Final = frozenset({"other"})
_ONE_OTHER: Final = frozenset({"one", "other"})
_ONE_MANY_OTHER: Final = frozenset({"one", "many", "other"})
_ONE_FEW_MANY_OTHER: Final = frozenset({"one", "few", "many", "other"})
_ONE_TWO_OTHER: Final = frozenset({"one", "two", "other"})
_ALL: Final = frozenset({"zero", "one", "two", "few", "many", "other"})

FALLBACK_RULE: Final[RuleSpec] = (_one_i1_v0, _ONE_OTHER)
"""The rule for languages without a built-in rule: ``one`` iff ``i = 1 and v = 0``."""

_PT_PT: Final[RuleSpec] = (_it_pt_pt, _ONE_MANY_OTHER)
_SLAVIC: Final[RuleSpec] = (_ru_uk, _ONE_FEW_MANY_OTHER)
_CJK: Final[RuleSpec] = (_other, _OTHER)

# CLDR 49 parentLocales: these inherit their plural rules from pt-PT, not pt.
_PT_PT_CHILDREN: Final = (
    "pt-AO",
    "pt-CH",
    "pt-CV",
    "pt-FR",
    "pt-GQ",
    "pt-GW",
    "pt-LU",
    "pt-MO",
    "pt-MZ",
    "pt-ST",
    "pt-TL",
)

BUILTIN_RULES: Final[Mapping[str, RuleSpec]] = MappingProxyType(
    {
        "en": FALLBACK_RULE,
        "de": FALLBACK_RULE,
        "nl": FALLBACK_RULE,
        "tr": (_one_n1, _ONE_OTHER),
        "es": (_es, _ONE_MANY_OTHER),
        "fr": (_fr_pt, _ONE_MANY_OTHER),
        "pt": (_fr_pt, _ONE_MANY_OTHER),
        "it": _PT_PT,
        "pt-PT": _PT_PT,
        **dict.fromkeys(_PT_PT_CHILDREN, _PT_PT),
        "ru": _SLAVIC,
        "uk": _SLAVIC,
        "pl": (_pl, _ONE_FEW_MANY_OTHER),
        "cs": (_cs, _ONE_FEW_MANY_OTHER),
        "ar": (_ar, _ALL),
        "he": (_he, _ONE_TWO_OTHER),
        "ja": _CJK,
        "zh": _CJK,
        "ko": _CJK,
    }
)
"""Rule and categories by canonical locale tag (read-only).

The 18 CLDR rule tags of the 17 built-in languages (``pt-PT`` has its own
rule), plus the CLDR 49 children of ``pt-PT``.
"""
