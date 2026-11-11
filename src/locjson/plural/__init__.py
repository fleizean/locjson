"""Plural entries and plural-form selection.

:mod:`locjson.plural.categories` holds the CLDR category names and the frozen
:class:`~locjson.plural.categories.PluralEntry` data model.
:mod:`locjson.plural.resolver` picks a form for a count. This package imports
nothing on its own, so each layer only pulls in the module it needs.
"""
