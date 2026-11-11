"""The :class:`Localizer`: lazy per-locale catalogs and ``t()`` lookups."""

from __future__ import annotations

import collections
import threading
from collections.abc import Callable
from typing import TYPE_CHECKING, Literal, TypeAlias

from locjson import _log
from locjson._compat import override
from locjson.catalog import build_catalog
from locjson.errors import (
    ConfigurationError,
    InterpolationError,
    InvalidLocaleError,
    LocJsonError,
    MissingTranslationError,
)
from locjson.loaders.filesystem import FilesystemLoader
from locjson.locale import fallback_chain, normalize
from locjson.plural.categories import PluralEntry
from locjson.plural.resolver import select_form

if TYPE_CHECKING:
    import os
    from collections.abc import Mapping, Sequence
    from decimal import Decimal
    from typing import NamedTuple

    from locjson.catalog import Catalog
    from locjson.formatting import Template
    from locjson.loaders.base import Loader

    class _Snapshot(NamedTuple):
        available: frozenset[str]
        catalogs: Mapping[str, Catalog]

else:
    # Functional form: class-syntax typing.NamedTuple imports ast on 3.14 (PKG-03).
    _Snapshot = collections.namedtuple("_Snapshot", ["available", "catalogs"])

__all__ = ["Localizer", "MissingPolicy"]

MissingPolicy: TypeAlias = Literal["key", "empty", "raise"] | Callable[[str, str], str]
"""What ``t()`` returns for a missing key: the key itself, ``""``, an error, or
the result of ``policy(key, locale)``."""

_MISSING_POLICIES = frozenset({"key", "empty", "raise"})


class Localizer:
    """Look up translations from JSON catalogs through a locale fallback chain.

    Catalogs are loaded lazily, once per locale, and kept as immutable
    snapshots, so a warm lookup is a dictionary access plus a join of
    precompiled segments with no file I/O.

    Args:
        path: A directory of ``<locale>.json`` files. Shorthand for
            ``loader=FilesystemLoader(path)``.
        loader: Any :class:`~locjson.Loader`. Pass exactly one of ``path`` and
            ``loader``.
        default_locale: The locale used when none is requested, and the last
            step of every fallback chain. It must be one of the discovered
            locales.
        fallbacks: Extra locales to try per locale, for example
            ``{"pt-BR": ["pt"]}``. A plain string value is one locale.
        missing: What ``t()`` does when no locale in the chain has the key:
            ``"key"`` (return the key), ``"empty"``, ``"raise"``, or a
            callable ``(key, locale) -> str``.
        preload: Load and validate every discovered locale up front.

    Raises:
        ConfigurationError: If both or neither of ``path`` and ``loader`` are
            given, ``missing`` is not a valid policy, the catalog directory does
            not exist, or ``default_locale`` is not a discovered locale.
        InvalidLocaleError: If ``default_locale`` or a ``fallbacks`` tag is not
            a valid locale tag.
        InvalidCatalogError: If discovery finds a file name that is not a valid
            locale tag.
    """

    __slots__ = (
        "_default",
        "_fallbacks",
        "_loader",
        "_lock",
        "_missing",
        "_preload",
        "_snapshot",
    )

    def __init__(
        self,
        path: str | os.PathLike[str] | None = None,
        *,
        loader: Loader | None = None,
        default_locale: str = "en",
        fallbacks: Mapping[str, Sequence[str] | str] | None = None,
        missing: MissingPolicy = "key",
        preload: bool = False,
    ) -> None:
        if path is not None:
            if loader is not None:
                msg = "pass either path= or loader=, not both"
                raise ConfigurationError(msg)
            loader = FilesystemLoader(path)
        elif loader is None:
            msg = "pass a catalog directory as path= or a Loader as loader="
            raise ConfigurationError(msg)
        if not (callable(missing) or missing in _MISSING_POLICIES):
            msg = (
                f"missing= must be 'key', 'empty', 'raise' or a callable, "
                f"got {missing!r}"
            )
            raise ConfigurationError(msg)
        self._loader: Loader = loader
        self._default = normalize(default_locale)
        self._fallbacks: dict[str, tuple[str, ...]] = {
            normalize(tag): _normalize_all(chain)
            for tag, chain in (fallbacks or {}).items()
        }
        self._missing: MissingPolicy = missing
        self._preload = preload
        self._lock = threading.Lock()
        available = frozenset(loader.discover_locales())
        if self._default not in available:
            msg = (
                f"default_locale {self._default!r} is not among the discovered "
                f"locales {sorted(available)}"
            )
            raise ConfigurationError(msg)
        self._snapshot = _Snapshot(available, {})

    @override
    def __repr__(self) -> str:
        return f"Localizer(loader={self._loader!r}, default_locale={self._default!r})"

    @property
    def locales(self) -> frozenset[str]:
        """The canonical tags of every discovered locale."""
        return self._snapshot.available

    @property
    def default_locale(self) -> str:
        """The canonical default locale."""
        return self._default

    def t(
        self,
        key: str,
        /,
        *,
        locale: str | None = None,
        count: int | float | Decimal | None = None,
        context: None = None,
        **variables: object,
    ) -> str:
        """Translate ``key``, trying each locale of the fallback chain in turn.

        Args:
            key: A flat dot key such as ``"nav.home"``.
            locale: The locale to translate into. Defaults to the default
                locale. An invalid tag falls back to the default locale.
            count: The quantity for plural messages. It is also available to
                templates as ``{count}``. A plural message without ``count``
                uses its ``other`` form.
            context: Reserved for a future version; must be ``None``.
            **variables: Placeholder values. A placeholder without a value is
                kept as literal ``{name}`` text.

        Returns:
            The rendered translation. When no locale in the chain has the key,
            the result of the ``missing`` policy (the key itself by default).

        Raises:
            LocJsonError: If ``context`` is not ``None``.
            MissingTranslationError: If the key is missing everywhere and the
                policy is ``"raise"``.
            InterpolationError: Under ``missing="raise"``, if a placeholder has
                no value or a plural message is called without ``count``.
            InvalidCatalogError: If a catalog needed for the lookup is invalid.
        """
        reserved: object = context  # typed None, but callers may pass anything
        if reserved is not None:
            msg = "context= is reserved for a future version of locjson"
            raise LocJsonError(msg)
        tag = self._resolve(locale)
        snapshot = self._snapshot
        strict = self._missing == "raise"
        for candidate in fallback_chain(tag, self._fallbacks, self._default):
            if candidate not in snapshot.available:
                continue
            catalog = snapshot.catalogs.get(candidate)
            if catalog is None:
                catalog = self._catalog(candidate)
            entry = catalog.get(key)
            if entry is None:
                continue
            if count is not None:
                variables["count"] = count
                if isinstance(entry, PluralEntry):
                    # The rules follow the catalog that supplied the entry.
                    entry = select_form(entry, catalog.locale, count)
            elif isinstance(entry, PluralEntry):
                entry = self._without_count(entry, key)
            return entry.render(variables, strict=strict, key=key)
        return self._on_missing(key, tag)

    def _without_count(self, entry: PluralEntry, key: str) -> Template:
        if self._missing == "raise":
            msg = f"plural key {key!r} needs count="
            raise InterpolationError(key, "count", msg)
        _log.debug("locjson: plural key %r called without count; using 'other'", key)
        return entry.other

    def _on_missing(self, key: str, tag: str) -> str:
        _log.debug("locjson: no translation for %r in %r or its fallbacks", key, tag)
        policy = self._missing
        if callable(policy):
            return policy(key, tag)
        if policy == "raise":
            raise MissingTranslationError(key, tag)
        return "" if policy == "empty" else key

    def _resolve(self, locale: str | None) -> str:
        if locale is None:
            return self._default
        try:
            return normalize(locale)
        except InvalidLocaleError:
            return self._default

    def _catalog(self, tag: str) -> Catalog:
        with self._lock:
            snapshot = self._snapshot
            catalog = snapshot.catalogs.get(tag)
            if catalog is None:
                catalog = build_catalog(tag, self._loader.load(tag)).unwrap()
                self._snapshot = _Snapshot(
                    snapshot.available, {**snapshot.catalogs, tag: catalog}
                )
            return catalog


def _normalize_all(tags: Sequence[str] | str) -> tuple[str, ...]:
    if isinstance(tags, str):
        return (normalize(tags),)
    return tuple(normalize(tag) for tag in tags)
