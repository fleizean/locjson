"""Choosing the plural form for a count.

0.1.0 ships one resolver, the CLDR default rule (``one`` for 1, ``other``
otherwise). Per-language rules replace :func:`default_resolver` in a later
version without changing :func:`select_form` or the catalog format.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, TypeAlias

if TYPE_CHECKING:
    from collections.abc import Callable
    from decimal import Decimal

    from locjson.formatting import Template
    from locjson.plural.categories import PluralEntry

__all__ = ["PluralResolver", "default_resolver", "select_form"]

PluralResolver: TypeAlias = "Callable[[str, int | float | Decimal], str]"
"""A function ``(locale, count) -> category name``."""


def default_resolver(locale: str, count: int | float | Decimal) -> str:  # noqa: ARG001
    """Apply the CLDR default rule: ``one`` for 1 and -1, ``other`` otherwise.

    ``1.0`` and ``Decimal("1")`` count as 1. The locale is ignored; it is part
    of the signature for per-language resolvers.

    Args:
        locale: The canonical locale of the catalog that holds the entry.
        count: The quantity.

    Returns:
        ``"one"`` or ``"other"``.
    """
    return "one" if abs(count) == 1 else "other"


def select_form(
    entry: PluralEntry,
    locale: str,
    count: int | float | Decimal,
    resolver: PluralResolver = default_resolver,
) -> Template:
    """Pick the form of ``entry`` to render for ``count``.

    A ``zero`` form wins for a count of zero in every language (the
    explicit-zero override). Otherwise ``resolver`` names a category, and
    ``other`` is used when the entry has no form for it.

    Args:
        entry: The plural entry.
        locale: The canonical locale of the catalog that supplied ``entry``,
            so the rules follow the text actually shown.
        count: The quantity.
        resolver: Maps ``(locale, count)`` to a category name.

    Returns:
        The template to render.
    """
    if count == 0:
        zero = entry.get("zero")
        if zero is not None:
            return zero
    form = entry.get(resolver(locale, count))
    return entry.other if form is None else form
