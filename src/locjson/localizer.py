"""The :class:`Localizer`: lazy per-locale catalogs and ``t()`` lookups."""

from __future__ import annotations

import collections
import os
import threading
from collections.abc import Callable, Mapping, Sequence
from typing import TYPE_CHECKING, Literal, TypeAlias, cast

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
    from decimal import Decimal
    from typing import NamedTuple

    from locjson.catalog import Catalog, Entry
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
_CHAIN_CACHE_MAX = 256
_TAG_LOG_LIMIT = 64
_STRICT_ENV = "LOCJSON_STRICT"
_TRUTHY = frozenset({"1", "true", "yes", "on"})
_FALSY = frozenset({"", "0", "false", "no", "off"})


class Localizer:
    """Look up translations from JSON catalogs through a locale fallback chain.

    Catalogs are loaded lazily, once per locale, and kept as immutable
    snapshots, so a warm lookup is a dictionary access plus a join of
    precompiled segments with no file I/O.

    Request-time locale tags (``t(locale=...)``, ``has(locale=...)``) only
    select among the discovered locales. An invalid tag falls back to
    ``default_locale`` with a DEBUG record and never reaches the loader.

    Args:
        path: A directory of ``<locale>.json`` files or ``<locale>/``
            directories. Shorthand for ``loader=FilesystemLoader(path)``.
        loader: Any :class:`~locjson.Loader`. Pass exactly one of ``path`` and
            ``loader``.
        default_locale: The locale used when none is requested, and the last
            step of every fallback chain. It must be one of the discovered
            locales.
        fallbacks: Extra locales to try per locale, for example
            ``{"pt-BR": ["pt"]}``. Each value is a list or tuple of tags.
        missing: What ``t()`` does when no locale in the chain has the key:
            ``"key"`` (return the key), ``"empty"``, ``"raise"``, or a
            callable ``(key, locale) -> str`` whose result is returned as-is.
            ``"raise"`` also makes missing variables and a missing ``count``
            raise :class:`~locjson.InterpolationError`.
        preload: Load and validate every discovered locale in the constructor,
            so a broken catalog fails at startup instead of at first use.
        strict: Make every slip raise, exactly as ``missing="raise"`` does,
            whatever ``missing`` says. ``None`` (the default) reads the
            ``LOCJSON_STRICT`` environment variable once, here: ``1``,
            ``true``, ``yes`` or ``on`` turn it on, and ``0``, ``false``,
            ``no``, ``off`` or an empty value leave it off (case-insensitive).
            For example ``strict=settings.DEBUG``.

    Slips (a missing key, a missing variable or a plural message without
    ``count``) are lenient unless strict. Each is logged on the ``locjson``
    logger at WARNING the first time per ``(kind, locale, key)`` for this
    Localizer, and at DEBUG afterwards. Records name keys, locales and
    placeholders, never variable values. Invalid request-time locale tags are
    logged at DEBUG only, because they come from request input.

    Raises:
        ConfigurationError: If both or neither of ``path`` and ``loader`` are
            given, ``loader`` is not a Loader, ``missing`` is not a valid
            policy, ``fallbacks`` is not a mapping of tags to lists of tags,
            ``strict`` is not a bool or ``None``, ``LOCJSON_STRICT`` holds
            another value, the catalog directory does not exist, or
            ``default_locale`` is not a discovered locale.
        InvalidLocaleError: If ``default_locale`` or a ``fallbacks`` tag is not
            a valid locale tag.
        InvalidCatalogError: If discovery finds a name that is not a valid
            locale tag, or ``preload=True`` and a catalog is invalid.
    """

    __slots__ = (
        "_chains",
        "_default",
        "_fallbacks",
        "_loader",
        "_lock",
        "_missing",
        "_on_variable",
        "_preload",
        "_raises",
        "_slips",
        "_snapshot",
        "_strict",
    )

    def __init__(
        self,
        path: str | os.PathLike[str] | None = None,
        *,
        loader: Loader | None = None,
        default_locale: str = "en",
        fallbacks: Mapping[str, Sequence[str]] | None = None,
        missing: MissingPolicy = "key",
        preload: bool = False,
        strict: bool | None = None,
    ) -> None:
        self._loader: Loader = _make_loader(path, loader)
        if not (callable(missing) or missing in _MISSING_POLICIES):
            msg = (
                f"missing= must be 'key', 'empty', 'raise' or a callable, "
                f"got {missing!r}"
            )
            raise ConfigurationError(msg)
        self._missing: MissingPolicy = missing
        self._strict = _resolve_strict(strict)
        # Every slip raises when strict or under missing="raise".
        self._raises = self._strict or missing == "raise"
        self._slips = _log.SlipLog()
        self._on_variable = self._slips.variable  # bound once, not per call
        self._default = normalize(default_locale)
        self._fallbacks = _normalize_fallbacks(fallbacks)
        self._preload = preload
        self._lock = threading.Lock()
        # Canonical tag -> fallback chain. Cleared when full (bounded, A8).
        self._chains: dict[str, tuple[str, ...]] = {}
        available = frozenset(self._loader.discover_locales())
        if self._default not in available:
            msg = (
                f"default_locale {self._default!r} is not among the discovered "
                f"locales {sorted(available)}"
            )
            raise ConfigurationError(msg)
        self._snapshot = _Snapshot(available, {})
        if preload:
            with self._lock:
                catalogs = {tag: self._build(tag) for tag in sorted(available)}
                self._snapshot = _Snapshot(available, catalogs)

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

    @property
    def strict(self) -> bool:
        """Whether every slip raises, as resolved at construction."""
        return self._strict

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
            key: A flat dot key such as ``"nav.home"``. Keys are compared
                exactly, with no case folding or Unicode normalization.
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
                Localizer is strict or the policy is ``"raise"``.
            InterpolationError: When strict or under ``missing="raise"``, if a
                placeholder has no value or a plural message is called without
                ``count``.
            InvalidCatalogError: If a catalog needed for the lookup is invalid.
        """
        reserved: object = context  # typed None, but callers may pass anything
        if reserved is not None:
            msg = "context= is reserved for a future version of locjson"
            raise LocJsonError(msg)
        tag = self._resolve_locale(locale)
        found = self._find(key, tag)
        if found is None:
            return self._on_missing(key, tag)
        entry, source = found
        if count is not None:
            variables["count"] = count
            if isinstance(entry, PluralEntry):
                # The rules follow the catalog that supplied the entry.
                entry = select_form(entry, source, count)
        elif isinstance(entry, PluralEntry):
            return self._without_count(entry, key, tag, variables)
        return entry.render(
            variables,
            strict=self._raises,
            key=key,
            locale=tag,
            on_missing=self._on_variable,
        )

    def has(self, key: str, /, *, locale: str | None = None) -> bool:
        """Tell whether some locale in the chain translates ``key``.

        Only real translations count: a non-empty string or a plural entry.
        Group prefixes such as ``"nav"`` and keys whose value is ``""`` or
        ``null`` are not translations. The ``missing`` policy is never used.

        Args:
            key: A flat dot key.
            locale: The locale whose chain is searched. Defaults to the
                default locale; an invalid tag falls back to it.

        Returns:
            ``True`` if a translation exists.

        Raises:
            InvalidCatalogError: If a catalog needed for the lookup is invalid.
        """
        return self._find(key, self._resolve_locale(locale)) is not None

    def _resolve_locale(self, locale: str | None) -> str:
        if locale is None:
            return self._default
        try:
            return normalize(locale)
        except InvalidLocaleError:
            # Request tags are attacker-controlled: log a truncated repr only.
            shown = str(locale)[:_TAG_LOG_LIMIT]
            _log.debug("locjson: invalid locale tag %r; using %r", shown, self._default)
            return self._default

    def _chain(self, tag: str) -> tuple[str, ...]:
        chains = self._chains
        chain = chains.get(tag)
        if chain is None:
            chain = fallback_chain(tag, self._fallbacks, self._default)
            if len(chains) >= _CHAIN_CACHE_MAX:
                chains.clear()
            chains[tag] = chain
        return chain

    def _find(self, key: str, tag: str) -> tuple[Entry, str] | None:
        snapshot = self._snapshot
        for candidate in self._chain(tag):
            if candidate not in snapshot.available:
                continue
            catalog = snapshot.catalogs.get(candidate)
            if catalog is None:
                catalog = self._catalog(candidate)
            entry = catalog.get(key)
            if entry is not None:
                return entry, catalog.locale
        return None

    def _without_count(
        self, entry: PluralEntry, key: str, tag: str, variables: dict[str, object]
    ) -> str:
        if self._raises:
            msg = f"plural key {key!r} needs count="
            raise InterpolationError(key, "count", msg)
        self._slips.report(
            "missing count",
            tag,
            key,
            "locjson: missing count for plural key %r in %r; using 'other'",
            key,
            tag,
        )

        def on_missing(key: str, locale: str, name: str) -> None:
            # The missing count is already reported; other names still are.
            if name != "count":
                self._on_variable(key, locale, name)

        return entry.other.render(variables, key=key, locale=tag, on_missing=on_missing)

    def _on_missing(self, key: str, tag: str) -> str:
        if self._raises:
            raise MissingTranslationError(key, tag)
        self._slips.report(
            "missing key",
            tag,
            key,
            "locjson: missing key %r in %r and its fallbacks",
            key,
            tag,
        )
        policy = self._missing
        if callable(policy):
            return policy(key, tag)
        return "" if policy == "empty" else key

    def _build(self, tag: str) -> Catalog:
        return build_catalog(tag, self._loader.load(tag)).unwrap()

    def _catalog(self, tag: str) -> Catalog:
        with self._lock:
            snapshot = self._snapshot
            catalog = snapshot.catalogs.get(tag)
            if catalog is None:
                catalog = self._build(tag)
                self._snapshot = _Snapshot(
                    snapshot.available, {**snapshot.catalogs, tag: catalog}
                )
            return catalog


def _make_loader(path: str | os.PathLike[str] | None, loader: object) -> Loader:
    if path is not None:
        if loader is not None:
            msg = "pass either path= or loader=, not both"
            raise ConfigurationError(msg)
        return FilesystemLoader(path)
    if loader is None:
        msg = "pass a catalog directory as path= or a Loader as loader="
        raise ConfigurationError(msg)
    # The structural check of runtime_checkable isinstance(), without its
    # inspect import on 3.12+.
    if not all(
        callable(getattr(loader, name, None)) for name in ("discover_locales", "load")
    ):
        msg = (
            "loader= must be a Loader with discover_locales() and load(), "
            f"got {type(loader).__name__}"
        )
        raise ConfigurationError(msg)
    return cast("Loader", loader)


def _resolve_strict(strict: object) -> bool:
    # Typed loosely on purpose: callers may pass anything at runtime.
    if isinstance(strict, bool):
        return strict
    if strict is not None:
        msg = f"strict= must be True, False or None, got {type(strict).__name__}"
        raise ConfigurationError(msg)
    raw = os.environ.get(_STRICT_ENV, "")
    value = raw.strip().lower()
    if value in _TRUTHY:
        return True
    if value in _FALSY:
        return False
    msg = (
        f"{_STRICT_ENV} must be one of 1/true/yes/on or 0/false/no/off "
        f"(or empty), got {raw[:_TAG_LOG_LIMIT]!r}"
    )
    raise ConfigurationError(msg)


def _normalize_fallbacks(fallbacks: object) -> dict[str, tuple[str, ...]]:
    # Typed loosely on purpose: callers may pass anything at runtime.
    if fallbacks is None:
        return {}
    if not isinstance(fallbacks, Mapping):
        msg = (
            "fallbacks= must be a mapping of locale tags to lists of tags, "
            f"got {type(fallbacks).__name__}"
        )
        raise ConfigurationError(msg)
    result: dict[str, tuple[str, ...]] = {}
    for tag, chain in fallbacks.items():
        if isinstance(chain, str) or not isinstance(chain, Sequence):
            msg = (
                f"fallbacks[{tag!r}] must be a list of locale tags, got "
                f"{type(chain).__name__}"
            )
            raise ConfigurationError(msg)
        tags: list[str] = []
        for item in chain:
            if not isinstance(item, str):
                msg = (
                    f"fallbacks[{tag!r}] must contain only locale tags, got "
                    f"{type(item).__name__}"
                )
                raise ConfigurationError(msg)
            tags.append(normalize(item))
        result[normalize(tag)] = tuple(tags)
    return result
