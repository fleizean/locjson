"""CLDR plural categories and the immutable :class:`PluralEntry`.

A plural entry is a catalog object whose keys are all CLDR plural categories,
with ``other`` present and every value a string::

    {"zero": "No messages", "one": "{count} message", "other": "{count} messages"}

This module is the data-model seam that later versions extend with per-language
rules; the file format it describes is frozen.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import TYPE_CHECKING, Final, Literal, TypeAlias

from locjson._compat import override

if TYPE_CHECKING:
    from collections.abc import Mapping

    from locjson.formatting import Template

__all__ = ["CATEGORIES", "CATEGORY_SET", "PluralCategory", "PluralEntry"]

PluralCategory: TypeAlias = Literal["zero", "one", "two", "few", "many", "other"]
"""One of the six CLDR plural category names."""

CATEGORIES: Final[tuple[PluralCategory, ...]] = (
    "zero",
    "one",
    "two",
    "few",
    "many",
    "other",
)
"""The CLDR plural categories, in CLDR order."""

CATEGORY_SET: Final[frozenset[str]] = frozenset(CATEGORIES)
""":data:`CATEGORIES` as a set, for membership tests."""


class PluralEntry:
    """The compiled forms of one plural message.

    Forms are stored in CLDR order whatever order they had in the file, so the
    choice of form never depends on JSON key order. Empty forms are not stored:
    the catalog validator drops them, and selection falls back to ``other``.

    Args:
        forms: Compiled templates by category name. ``other`` is required.

    Raises:
        ValueError: If ``other`` is missing or a key is not a plural category.
    """

    __slots__ = ("_fields", "_forms", "_other")

    _fields: frozenset[str]
    _forms: Mapping[str, Template]
    _other: Template

    def __init__(self, forms: Mapping[str, Template]) -> None:
        unknown = sorted(set(forms) - CATEGORY_SET)
        if unknown:
            msg = f"not a plural category: {', '.join(map(repr, unknown))}"
            raise ValueError(msg)
        if "other" not in forms:
            msg = "a plural entry needs an 'other' form"
            raise ValueError(msg)
        ordered = {name: forms[name] for name in CATEGORIES if name in forms}
        fields = frozenset().union(*(form.fields for form in ordered.values()))
        object.__setattr__(self, "_forms", MappingProxyType(ordered))
        object.__setattr__(self, "_other", ordered["other"])
        object.__setattr__(self, "_fields", fields)

    @override
    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError(f"{type(self).__name__} is immutable")

    @override
    def __repr__(self) -> str:
        forms = ", ".join(
            f"{name}={form.source!r}" for name, form in self._forms.items()
        )
        return f"PluralEntry({forms})"

    @override
    def __eq__(self, other: object) -> bool:
        if not isinstance(other, PluralEntry):
            return NotImplemented
        return dict(self._forms) == dict(other._forms)

    @override
    def __hash__(self) -> int:
        return hash(tuple(self._forms.items()))

    @property
    def forms(self) -> Mapping[str, Template]:
        """Read-only mapping of category name to template, in CLDR order."""
        return self._forms

    @property
    def other(self) -> Template:
        """The ``other`` form, used when no better form exists."""
        return self._other

    @property
    def fields(self) -> frozenset[str]:
        """Every placeholder name used by any form."""
        return self._fields

    def get(self, category: str) -> Template | None:
        """Return the form for ``category``, or ``None`` when it is absent.

        Args:
            category: A plural category name such as ``"one"``.

        Returns:
            The compiled form or ``None``.
        """
        return self._forms.get(category)
