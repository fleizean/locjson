"""Choosing the plural form for a count.

The plural rule of a catalog is found in three steps:

1. The built-in CLDR 49 rules, tried for the exact canonical tag, then for
   the tag's script-aware parents (:func:`locjson.locale.parents`), then for
   its language subtag. Built-in languages always use these rules, whether
   or not Babel is installed.
2. Babel's CLDR rules, when ``locjson[babel]`` is installed, tried for the
   same candidates in the same order. The first one Babel knows wins.
3. Otherwise the one/other rule (``one`` iff ``i = 1 and v = 0``).

Lookups are cached (bounded), and each :class:`~locjson.Localizer` resolves
the rule once per catalog, at load, so a warm lookup does no Babel work.
"""

from __future__ import annotations

import functools
from typing import TYPE_CHECKING

from locjson.locale import parents
from locjson.plural._babel import babel_rule
from locjson.plural.rules import BUILTIN_RULES, FALLBACK_RULE

if TYPE_CHECKING:
    from locjson.formatting import Template
    from locjson.plural.categories import PluralEntry
    from locjson.plural.operands import Operands
    from locjson.plural.rules import PluralRule, RuleSpec

__all__ = ["rule_for", "select_form"]


def rule_for(tag: str) -> PluralRule:
    """Return the plural rule for a locale.

    Args:
        tag: A canonical locale tag, as produced by
            :func:`locjson.locale.normalize`.

    Returns:
        A function from :class:`~locjson.plural.operands.Operands` to a CLDR
        plural category name.
    """
    return _lookup(tag)[0]


@functools.lru_cache(maxsize=256)
def _lookup(tag: str) -> RuleSpec:
    language = tag.partition("-")[0]
    candidates = tuple(dict.fromkeys((tag, *parents(tag), language)))
    for candidate in candidates:
        spec = BUILTIN_RULES.get(candidate)
        if spec is not None:
            return spec
    for candidate in candidates:
        spec = babel_rule(candidate)
        if spec is not None:
            return spec
    return FALLBACK_RULE


def select_form(entry: PluralEntry, operands: Operands, rule: PluralRule) -> Template:
    """Pick the form of ``entry`` to render for a count.

    A ``zero`` form wins for a count of zero in every language (the
    explicit-zero override), without asking the rule. Otherwise ``rule`` names
    a category, and ``other`` is used when the entry has no form for it.

    Args:
        entry: The plural entry.
        operands: The operands of the count.
        rule: The plural rule of the catalog that supplied ``entry``, so the
            rule follows the text actually shown.

    Returns:
        The template to render.
    """
    if operands.n == 0:
        zero = entry.get("zero")
        if zero is not None:
            return zero
    form = entry.get(rule(operands))
    return entry.other if form is None else form
