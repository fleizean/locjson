"""The :class:`Localizer`: lazy per-locale catalogs and ``t()`` lookups."""

from __future__ import annotations

import collections
import contextlib
import os
import threading
from collections.abc import Callable, Mapping, Sequence
from typing import TYPE_CHECKING, Literal, TypeAlias, cast

from locjson import _log
from locjson import locale as _locale
from locjson._compat import override
from locjson.catalog import build_catalog
from locjson.context import LocaleContext
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
from locjson.plural.operands import plural_operands
from locjson.plural.resolver import rule_for, select_form
from locjson.translator import Translator

if TYPE_CHECKING:
    from collections.abc import Iterator
    from decimal import Decimal
    from typing import NamedTuple, SupportsIndex

    from locjson.catalog import Catalog, Entry
    from locjson.loaders.base import Loader
    from locjson.plural.rules import PluralRule

    class _Snapshot(NamedTuple):
        available: frozenset[str]
        catalogs: Mapping[str, Catalog]
        # The plural rule of each catalog, keyed exactly like catalogs.
        rules: Mapping[str, PluralRule]

else:
    # Functional form: class-syntax typing.NamedTuple imports ast on 3.14 (PKG-03).
    _Snapshot = collections.namedtuple("_Snapshot", ["available", "catalogs", "rules"])

__all__ = ["Localizer", "MissingPolicy"]

MissingPolicy: TypeAlias = Literal["key", "empty", "raise"] | Callable[[str, str], str]
"""What ``t()`` returns for a missing key: the key itself, ``""``, an error, or
the result of ``policy(key, locale)``."""

_MISSING_POLICIES = frozenset({"key", "empty", "raise"})
_CHAIN_CACHE_MAX = 256
_TAG_LOG_LIMIT = 64
_UNREADABLE_COUNT = "count could not be read as a number"
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

    Slips (a missing key, a missing variable, a plural message without
    ``count`` or an invalid ``count``) are lenient unless strict. Each is
    logged on the ``locjson`` logger at WARNING the first time per
    ``(kind, locale, key)`` for this Localizer, and at DEBUG afterwards.
    Records name keys, locales, placeholders and the type or problem of an
    invalid count, never variable or count values. Invalid request-time
    locale tags are logged at DEBUG only, because they come from request
    input.

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
        "_context",
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
        self._context = LocaleContext()
        # Canonical tag -> fallback chain. Cleared when full (bounded, A8).
        self._chains: dict[str, tuple[str, ...]] = {}
        available = frozenset(self._loader.discover_locales())
        if self._default not in available:
            msg = (
                f"default_locale {self._default!r} is not among the discovered "
                f"locales {sorted(available)}"
            )
            raise ConfigurationError(msg)
        self._snapshot = _Snapshot(available, {}, {})
        if preload:
            with self._lock:
                catalogs = {tag: self._build(tag) for tag in sorted(available)}
                self._snapshot = _publish(available, catalogs)

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

    @property
    def current_locale(self) -> str:
        """The locale of the current context, or ``default_locale`` if none is set.

        It is set with :meth:`use` or :meth:`set_locale` and is private to this
        Localizer and to the current asyncio task or thread.
        """
        current = self._context.get()
        return self._default if current is None else current

    def set_locale(self, locale: str) -> None:
        """Set the current locale for the rest of the current context.

        The value is per context: it applies to the calling asyncio task or
        thread only, from now until it ends or the locale is set again. Prefer
        :meth:`use` in code that runs on a reused worker (a thread pool), since
        a value set here stays in that worker's context.

        Args:
            locale: A locale tag such as ``"tr"`` or ``"pt_BR"``. An invalid tag
                clears the current locale, so lookups use ``default_locale``,
                and is logged at DEBUG.
        """
        self._context.set(self._canonical(locale))

    @contextlib.contextmanager
    def use(self, locale: str) -> Iterator[str]:
        """Use ``locale`` as the current locale inside a ``with`` block.

        On exit the previous current locale is restored, including when the
        block raises. Blocks nest, and the value is private to the current
        asyncio task or thread.

        Example:
            >>> with l10n.use("tr"):  # doctest: +SKIP
            ...     l10n.t("nav.home")
            'Ana Sayfa'

        Args:
            locale: A locale tag. An invalid tag means ``default_locale`` inside
                the block and is logged at DEBUG.

        Yields:
            The canonical locale in effect inside the block.
        """
        tag = self._canonical(locale)
        with self._context.use(tag):
            yield self._default if tag is None else tag

    def reload(self) -> None:
        """Re-discover the locales and rebuild every loaded catalog, atomically.

        Discovery runs again, so added locales appear and removed ones
        disappear from :attr:`locales`. Every catalog loaded so far (every
        locale with ``preload=True``) is rebuilt from its files. Locales that
        were never loaded stay lazy.

        The swap is all or nothing. Everything is built first, and only when
        every catalog is valid does the new set replace the old one, in a
        single assignment. Each lookup reads one consistent set, so a
        concurrent ``t()`` sees either the old catalogs or the new ones, never
        a mix. When anything fails, the error propagates and lookups keep
        serving the previous catalogs.

        Locales that were never loaded are read when first needed, from the
        files as they are then.

        Raises:
            InvalidCatalogError: If a discovered name is not a valid locale tag
                or a rebuilt catalog is invalid (for example a half-written
                file).
            ConfigurationError: If the catalog directory is gone, or
                ``default_locale`` is no longer among the discovered locales.
        """
        with self._lock:
            available = frozenset(self._loader.discover_locales())
            if self._default not in available:
                msg = (
                    f"default_locale {self._default!r} is no longer among the "
                    f"discovered locales {sorted(available)}"
                )
                raise ConfigurationError(msg)
            loaded = self._snapshot.catalogs
            targets = available if self._preload else available & loaded.keys()
            catalogs = {tag: self._build(tag) for tag in sorted(targets)}
            # Chains do not depend on availability, so _chains stays valid.
            self._snapshot = _publish(available, catalogs)

    def for_locale(self, locale: str) -> Translator:
        """Return a :class:`~locjson.Translator` bound to ``locale``.

        The Translator uses ``locale`` for every call unless the call passes
        ``locale=``, and never reads or changes :attr:`current_locale`. Use
        it where no request context exists: background jobs, scheduled tasks,
        e-mails in a user's language.

        Example:
            >>> l10n.for_locale(user.language)("nav.home")  # doctest: +SKIP
            'Ana Sayfa'

        Args:
            locale: A locale tag. It is normalized once, here; an invalid tag
                binds :attr:`default_locale` and is logged at DEBUG.

        Returns:
            A new Translator with no prefix.
        """
        tag = self._canonical(locale)
        return Translator(self, locale=self._default if tag is None else tag)

    def scope(self, prefix: str) -> Translator:
        """Return a :class:`~locjson.Translator` that prepends ``prefix`` to keys.

        ``l10n.scope("inbox")("messages")`` looks up ``"inbox.messages"``.
        The Translator follows :attr:`current_locale`; chain
        :meth:`Translator.for_locale` to bind a locale as well.

        Args:
            prefix: A key prefix such as ``"inbox"`` or ``"settings.profile"``.

        Returns:
            A new Translator with no bound locale.

        Raises:
            ConfigurationError: If ``prefix`` is empty, starts or ends with
                ``"."``, has an empty segment or a segment starting with
                ``"$"``.
        """
        return Translator(self, prefix=prefix)

    def negotiate(self, accept_language: str | None) -> str:
        """Pick the best discovered locale for an ``Accept-Language`` header.

        This is :func:`locjson.negotiate` over :attr:`locales`, with
        :attr:`default_locale` as the fallback. Malformed headers never raise.

        Example:
            >>> l10n.negotiate("tr-TR,tr;q=0.9,en;q=0.8")  # doctest: +SKIP
            'tr'

        Args:
            accept_language: The header value, or ``None`` when it is absent.

        Returns:
            A canonical tag from :attr:`locales`, or :attr:`default_locale`.
        """
        return _locale.negotiate(accept_language, self.locales, self._default)

    def direction(self, locale: str | None = None) -> Literal["ltr", "rtl"]:
        """Return the text direction of a locale.

        The catalogs along the locale's fallback chain are checked first, in
        order, and the first ``$meta.direction`` found wins. When none
        declares one, the built-in table of :func:`locjson.direction` decides
        for the requested locale.

        Args:
            locale: A locale tag. Defaults to :attr:`current_locale`; an
                invalid tag falls back to the default locale.

        Returns:
            ``"ltr"`` or ``"rtl"``.

        Raises:
            InvalidCatalogError: If a catalog that has to be loaded is invalid.
        """
        tag = self._resolve_locale(locale)
        chain = self._chain(tag)
        while True:
            snapshot = self._snapshot  # one snapshot per attempt, as in _find
            for candidate in chain:
                if candidate not in snapshot.available:
                    continue
                catalog = snapshot.catalogs.get(candidate)
                if catalog is None:
                    self._load(candidate)
                    break
                declared = catalog.direction
                if declared is not None:
                    return "rtl" if declared == "rtl" else "ltr"
            else:
                return _locale.direction(tag)

    def t(
        self,
        key: str,
        /,
        *,
        locale: str | None = None,
        count: int | float | Decimal | SupportsIndex | None = None,
        context: None = None,
        **variables: object,
    ) -> str:
        """Translate ``key``, trying each locale of the fallback chain in turn.

        Args:
            key: A flat dot key such as ``"nav.home"``. Keys are compared
                exactly, with no case folding or Unicode normalization.
            locale: The locale to translate into. Defaults to
                :attr:`current_locale`. An invalid tag falls back to the
                default locale.
            count: The quantity for plural messages: an ``int``, ``float`` or
                ``Decimal``, or another integer type with ``__index__``, such
                as NumPy's ``np.int64``. The form follows the CLDR plural rule
                of the catalog that holds the message, and a ``zero`` form
                wins for any count equal to 0. ``Decimal`` counts keep their
                visible fraction digits (``Decimal("1.0")`` is ``other`` in
                English, ``one`` in Turkish); a float, including a subclass
                such as ``np.float64``, is read through the shortest ``repr``
                of its value. ``count`` is also available to templates as
                ``{count}``. A plural message without ``count`` uses its
                ``other`` form. An invalid count (a ``bool``, a string, NaN,
                an infinity, any other type, such as ``Fraction``, or more
                than 1000 integer or fraction digits) is a slip: the
                ``other`` form is used and ``{count}`` stays literal.
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
                placeholder has no value, a plural message is called without
                ``count``, or ``count`` is invalid.
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
        entry, rule = found
        if count is not None:
            try:
                operands = plural_operands(count)
            except (TypeError, ValueError) as error:
                # The message names the type or problem, never the value.
                return self._invalid_count(entry, key, tag, variables, str(error))
            except ArithmeticError:
                # Defense in depth: plural_operands never runs a count's own
                # arithmetic, but a failure must still be a slip. Its text
                # might show the value, so it is not used.
                return self._invalid_count(
                    entry, key, tag, variables, _UNREADABLE_COUNT
                )
            variables["count"] = count
            if isinstance(entry, PluralEntry):
                # The rule follows the catalog that supplied the entry.
                entry = select_form(entry, operands, rule)
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
            locale: The locale whose chain is searched. Defaults to
                :attr:`current_locale`; an invalid tag falls back to the
                default locale.

        Returns:
            ``True`` if a translation exists.

        Raises:
            InvalidCatalogError: If a catalog needed for the lookup is invalid.
        """
        return self._find(key, self._resolve_locale(locale)) is not None

    def _resolve_locale(self, locale: str | None) -> str:
        # Explicit locale= first, then the current context, then the default.
        if locale is None:
            current = self._context.get()
            return self._default if current is None else current
        tag = self._canonical(locale)
        return self._default if tag is None else tag

    def _canonical(self, locale: str) -> str | None:
        try:
            return normalize(locale)
        except InvalidLocaleError:
            # Request tags are attacker-controlled: log a truncated repr only.
            shown = str(locale)[:_TAG_LOG_LIMIT]
            _log.debug("locjson: invalid locale tag %r; using %r", shown, self._default)
            return None

    def _chain(self, tag: str) -> tuple[str, ...]:
        chains = self._chains
        chain = chains.get(tag)
        if chain is None:
            chain = fallback_chain(tag, self._fallbacks, self._default)
            if len(chains) >= _CHAIN_CACHE_MAX:
                chains.clear()
            chains[tag] = chain
        return chain

    def _find(self, key: str, tag: str) -> tuple[Entry, PluralRule] | None:
        chain = self._chain(tag)
        while True:
            # One snapshot per attempt: never mix catalogs of two generations.
            snapshot = self._snapshot
            catalogs = snapshot.catalogs
            for candidate in chain:
                if candidate not in snapshot.available:
                    continue
                catalog = catalogs.get(candidate)
                if catalog is None:
                    # Restart from the snapshot that _load published, which
                    # may also hold a reload's newer catalogs.
                    self._load(candidate)
                    break
                entry = catalog.get(key)
                if entry is not None:
                    # The rule of the same snapshot as the catalog.
                    return entry, snapshot.rules[candidate]
            else:
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
        return self._render_without_count(entry, key, tag, variables)

    def _invalid_count(
        self,
        entry: Entry,
        key: str,
        tag: str,
        variables: dict[str, object],
        reason: str,
    ) -> str:
        # ``reason`` names the count's type or problem; the value may come
        # from request input and is never logged or put in an error.
        if self._raises:
            msg = f"invalid count for key {key!r}: {reason}"
            raise InterpolationError(key, "count", msg)
        self._slips.report(
            "invalid count",
            tag,
            key,
            "locjson: invalid count for key %r in %r (%s); using 'other'",
            key,
            tag,
            reason,
        )
        return self._render_without_count(entry, key, tag, variables)

    def _render_without_count(
        self, entry: Entry, key: str, tag: str, variables: dict[str, object]
    ) -> str:
        # The other form of a plural, or the plain template, with {count}
        # left literal. Only reached on the lenient slip paths.
        template = entry.other if isinstance(entry, PluralEntry) else entry
        return template.render(
            variables, key=key, locale=tag, on_missing=self._on_variable_but_count
        )

    def _on_variable_but_count(self, key: str, locale: str, name: str) -> None:
        # The count slip is already reported; other missing names still are.
        if name != "count":
            self._on_variable(key, locale, name)

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

    def _load(self, tag: str) -> None:
        # Builds into the *current* snapshot, and only a locale it still
        # lists: each caller restarts afterwards, so every restart either adds
        # a catalog or observes a newer generation. A failed build publishes
        # nothing, so the next attempt builds again.
        with self._lock:
            snapshot = self._snapshot
            if tag in snapshot.available and tag not in snapshot.catalogs:
                catalog = self._build(tag)
                self._snapshot = _Snapshot(
                    snapshot.available,
                    {**snapshot.catalogs, tag: catalog},
                    {**snapshot.rules, tag: rule_for(tag)},
                )


def _publish(available: frozenset[str], catalogs: Mapping[str, Catalog]) -> _Snapshot:
    # The plural rule of each catalog is resolved here, once, at load.
    rules = {tag: rule_for(tag) for tag in catalogs}
    return _Snapshot(available, catalogs, rules)


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
