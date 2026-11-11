"""Plural entries and plural-form selection.

The package exposes :func:`categories_for`, the plural categories a locale
needs. Importing it loads :mod:`locjson.plural.resolver`; Babel is still only
imported when a rule is looked up for a language without a built-in rule.

Submodules:

* :mod:`locjson.plural.categories`: the CLDR category names and the frozen
  :class:`~locjson.plural.categories.PluralEntry` data model.
* :mod:`locjson.plural.operands`: the CLDR plural operands of a count.
* :mod:`locjson.plural.rules`: the built-in CLDR 49 rules.
* :mod:`locjson.plural.resolver`: rule lookup and plural-form selection.
* ``locjson.plural._babel``: the private adapter for the optional Babel extra.
"""

from __future__ import annotations

from locjson.plural.resolver import categories_for

__all__ = ["categories_for"]
