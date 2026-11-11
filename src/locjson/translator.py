"""Bound translators: a :class:`~locjson.Localizer` with a fixed locale or prefix."""

from __future__ import annotations

from typing import TYPE_CHECKING

from locjson._compat import override
from locjson.errors import ConfigurationError

if TYPE_CHECKING:
    from decimal import Decimal

    from locjson.localizer import Localizer

__all__ = ["Translator"]


class Translator:
    """Translate with a bound locale, a bound key prefix, or both.

    Get one from :meth:`Localizer.for_locale` or :meth:`Localizer.scope`, and
    combine them freely: ``l10n.scope("inbox").for_locale("tr")`` and
    ``l10n.for_locale("tr").scope("inbox")`` are equivalent, and nested scopes
    join with ``"."``.

    A Translator is immutable and safe to share between threads and tasks.

    - A bound locale is used for every call unless the call passes
      ``locale=``. It never reads or changes the Localizer's current locale,
      so it suits background jobs and e-mails sent in a user's language.
    - Without a bound locale, calls use the Localizer's current locale.
    - A prefix is prepended to every key: ``scope("inbox")("messages")``
      looks up ``"inbox.messages"``.

    Every call goes through the Localizer, so a Translator serves the
    catalogs of the latest :meth:`Localizer.reload` and follows the
    Localizer's ``missing`` policy and ``strict`` setting.

    Example:
        >>> nav = l10n.scope("nav").for_locale("tr")  # doctest: +SKIP
        >>> nav("home")  # doctest: +SKIP
        'Ana Sayfa'

    Args:
        localizer: The Localizer that does the lookups.
        locale: A canonical locale tag to bind, or ``None``. Use
            :meth:`Localizer.for_locale` to bind a tag that still needs
            normalizing.
        prefix: A key prefix such as ``"inbox"`` or ``"settings.profile"``, or
            ``None``.

    Raises:
        ConfigurationError: If ``prefix`` is empty, starts or ends with
            ``"."``, has an empty segment (``"a..b"``) or a segment starting
            with ``"$"``.
    """

    __slots__ = ("_locale", "_localizer", "_prefix")

    _locale: str | None
    _localizer: Localizer
    _prefix: str | None

    def __init__(
        self,
        localizer: Localizer,
        *,
        locale: str | None = None,
        prefix: str | None = None,
    ) -> None:
        if prefix is not None:
            _check_prefix(prefix)
        object.__setattr__(self, "_localizer", localizer)
        object.__setattr__(self, "_locale", locale)
        object.__setattr__(self, "_prefix", prefix)

    @override
    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError(f"{type(self).__name__} is immutable")

    @override
    def __delattr__(self, name: str) -> None:
        raise AttributeError(f"{type(self).__name__} is immutable")

    @override
    def __repr__(self) -> str:
        return f"Translator(locale={self._locale!r}, prefix={self._prefix!r})"

    @property
    def locale(self) -> str | None:
        """The bound canonical locale tag, or ``None`` when not bound."""
        return self._locale

    @property
    def prefix(self) -> str | None:
        """The bound key prefix, or ``None`` when not scoped."""
        return self._prefix

    def __call__(
        self,
        key: str,
        /,
        *,
        locale: str | None = None,
        count: int | float | Decimal | None = None,
        context: None = None,
        **variables: object,
    ) -> str:
        """Translate ``key`` as :meth:`Localizer.t` does.

        Args:
            key: A dot key, relative to the prefix when one is bound.
            locale: A locale that overrides the bound one for this call.
            count: The quantity for plural messages, also available as
                ``{count}``.
            context: Reserved for a future version; must be ``None``.
            **variables: Placeholder values.

        Returns:
            The rendered translation, or the result of the ``missing`` policy.

        Raises:
            LocJsonError: If ``context`` is not ``None``.
            MissingTranslationError: If the key is missing and slips raise.
            InterpolationError: If a value is missing and slips raise.
            InvalidCatalogError: If a catalog needed for the lookup is invalid.
        """
        prefix = self._prefix
        return self._localizer.t(
            key if prefix is None else f"{prefix}.{key}",
            locale=self._locale if locale is None else locale,
            count=count,
            context=context,
            **variables,
        )

    t = __call__

    def has(self, key: str, /, *, locale: str | None = None) -> bool:
        """Tell whether ``key`` has a translation, as :meth:`Localizer.has` does.

        Args:
            key: A dot key, relative to the prefix when one is bound.
            locale: A locale that overrides the bound one for this call.

        Returns:
            ``True`` if a translation exists.

        Raises:
            InvalidCatalogError: If a catalog needed for the lookup is invalid.
        """
        prefix = self._prefix
        return self._localizer.has(
            key if prefix is None else f"{prefix}.{key}",
            locale=self._locale if locale is None else locale,
        )

    def for_locale(self, locale: str) -> Translator:
        """Return a Translator like this one, bound to ``locale`` instead.

        Args:
            locale: A locale tag. It is normalized once, here; an invalid tag
                binds the default locale and is logged at DEBUG.

        Returns:
            A new Translator with the same prefix.
        """
        bound = self._localizer.for_locale(locale).locale
        return Translator(self._localizer, locale=bound, prefix=self._prefix)

    def scope(self, prefix: str) -> Translator:
        """Return a Translator like this one, with ``prefix`` appended.

        Args:
            prefix: A key prefix, joined to the current one with ``"."``.

        Returns:
            A new Translator with the same bound locale.

        Raises:
            ConfigurationError: If ``prefix`` is not a valid prefix.
        """
        _check_prefix(prefix)
        joined = prefix if self._prefix is None else f"{self._prefix}.{prefix}"
        return Translator(self._localizer, locale=self._locale, prefix=joined)


def _check_prefix(prefix: object) -> None:
    # Typed loosely on purpose: callers may pass anything at runtime.
    if not isinstance(prefix, str) or not prefix:
        msg = f"a scope prefix must be a non-empty string, got {prefix!r}"
        raise ConfigurationError(msg)
    for segment in prefix.split("."):
        if not segment:
            msg = (
                f"scope prefix {prefix!r} has an empty segment "
                "(a leading, trailing or doubled '.')"
            )
            raise ConfigurationError(msg)
        if segment.startswith("$"):
            msg = (
                f"scope prefix {prefix!r} has a segment starting with '$'; "
                "such keys are never translations"
            )
            raise ConfigurationError(msg)
