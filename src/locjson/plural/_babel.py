"""The optional Babel adapter, used when ``locjson[babel]`` is installed.

It gives full CLDR plural rules to languages without a built-in rule.
``babel`` is imported inside :func:`babel_rule` only, never at module level,
so ``import locjson`` stays free of it (PKG-03), and nothing imports Babel
until a catalog in such a language is loaded.

Security note: Babel turns CLDR rule text into Python code with ``eval``
inside its own ``babel.plural.to_python``. That runs only when the extra is
installed, and only on the CLDR data bundled with Babel, never on locjson
input. locjson passes Babel nothing but the canonical tag of a discovered
catalog.
"""

from __future__ import annotations

import decimal
from typing import TYPE_CHECKING, Final

from locjson.plural.operands import MAX_COUNT_DIGITS

if TYPE_CHECKING:
    from locjson.plural.operands import Operands
    from locjson.plural.rules import RuleSpec

__all__ = ["babel_rule"]

# Enough precision for any count plural_operands accepts (at most
# MAX_COUNT_DIGITS integer and fraction digits each), with no traps.
_EXACT: Final = decimal.Context(prec=2 * MAX_COUNT_DIGITS + 2, traps=[])


def babel_rule(tag: str) -> RuleSpec | None:
    """Return Babel's plural rule for a locale, if Babel is installed and knows it.

    The rule is compiled here, once, so a later :meth:`~locjson.Localizer.t`
    call does no Babel work beyond calling it.

    Args:
        tag: A canonical locale tag, as produced by
            :func:`locjson.locale.normalize`.

    Returns:
        The rule and the categories it can return (always including
        ``"other"``), or ``None`` when Babel is not installed, does not know
        the locale or cannot parse the tag.
    """
    try:
        from babel import Locale, UnknownLocaleError
    except ImportError:
        return None
    try:
        plural = Locale.parse(tag, sep="-").plural_form
        plural(0)  # Babel compiles the rule on its first call.
    except (UnknownLocaleError, ValueError, TypeError):
        return None

    def rule(operands: Operands) -> str:
        if operands.v == 0:
            # A whole count, as a plain int: exact, with no decimal context.
            return plural(operands.i)
        # Babel starts with abs(n), which rounds a Decimal to the current
        # context and may trap. Its own exact, non-trapping context keeps
        # every digit and never raises out of t().
        with decimal.localcontext(_EXACT):
            return plural(operands.n)

    return rule, frozenset(plural.tags) | {"other"}
