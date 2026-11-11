"""Choosing the plural form for a count.

The plural rule of a catalog is found in three steps:

1. The built-in CLDR 49 rules, tried for the exact canonical tag, then for
   the tag's script-aware parents (:func:`locjson.locale.parents`), then for
   its language subtag. A tag that spells out the language's likely script
   is also tried without it, right after itself, so ``pt-Latn-PT`` finds the
   ``pt-PT`` rule. Built-in languages always use these rules, whether or not
   Babel is installed.
2. Babel's CLDR rules, when ``locjson[babel]`` is installed, tried for the
   same candidates in the same order. The first one Babel knows wins.
3. Otherwise the one/other rule (``one`` iff ``i = 1 and v = 0``).

Lookups are cached (bounded), and each :class:`~locjson.Localizer` resolves
the rule once per catalog, at load, so a warm lookup does no Babel work.
"""

from __future__ import annotations

import functools
from typing import TYPE_CHECKING

from locjson.locale import _without_likely_script, normalize, parents
from locjson.plural._babel import babel_rule
from locjson.plural.rules import BUILTIN_RULES, FALLBACK_RULE

if TYPE_CHECKING:
    from collections.abc import Iterator

    from locjson.formatting import Template
    from locjson.plural.categories import PluralEntry
    from locjson.plural.operands import Operands
    from locjson.plural.rules import PluralRule, RuleSpec

__all__ = ["categories_for", "rule_for", "select_form"]


def categories_for(locale: str) -> frozenset[str]:
    """Return the plural categories a locale's plural rule can produce.

    These are the forms a plural entry in that locale may need. The set always
    contains ``"other"``. The rule is found the same way
    :meth:`~locjson.Localizer.t` finds it: the built-in CLDR rule, then
    Babel's rule when ``locjson[babel]`` is installed, then the one/other
    rule.

    The set is unordered. To list it in CLDR order, sort it with
    :data:`locjson.plural.categories.CATEGORIES`::

        sorted(categories_for("ar"), key=CATEGORIES.index)

    Example:
        >>> sorted(categories_for("ru"))
        ['few', 'many', 'one', 'other']

    Args:
        locale: A locale tag, in any spelling :func:`locjson.locale.normalize`
            accepts (``"pt_PT"`` and ``"pt-PT"`` are the same locale).

    Returns:
        The CLDR category names, out of ``zero``, ``one``, ``two``, ``few``,
        ``many`` and ``other``.

    Raises:
        InvalidLocaleError: If ``locale`` is not a valid locale tag.
    """
    return _lookup(normalize(locale))[1]


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


def _candidates(tag: str) -> Iterator[str]:
    # Each tag is followed by its spelling without an implied script, so
    # pt-Latn-PT finds the pt-PT rule before falling back to pt.
    for candidate in (tag, *parents(tag)):
        yield candidate
        bare = _without_likely_script(candidate)
        if bare is not None:
            yield bare
    yield tag.partition("-")[0]


@functools.lru_cache(maxsize=256)
def _lookup(tag: str) -> RuleSpec:
    candidates = tuple(dict.fromkeys(_candidates(tag)))
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
