"""Typed, zero-dependency JSON localization for Python.

Use a :class:`Localizer` directly, or install a default one with
:func:`setup` and call the module-level :func:`t`, :func:`has`, :func:`use`,
:func:`set_locale`, :func:`for_locale` and :func:`scope`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from locjson._version import __version__
from locjson.errors import (
    ConfigurationError,
    InterpolationError,
    InvalidCatalogError,
    InvalidLocaleError,
    LocJsonError,
    MissingTranslationError,
)
from locjson.loaders import DictLoader, FilesystemLoader, Loader, RawSource
from locjson.locale import direction, negotiate
from locjson.localizer import Localizer
from locjson.translator import Translator

if TYPE_CHECKING:
    import os
    from collections.abc import Mapping, Sequence
    from contextlib import AbstractContextManager
    from decimal import Decimal

    from locjson.localizer import MissingPolicy

__all__ = [
    "ConfigurationError",
    "DictLoader",
    "FilesystemLoader",
    "InterpolationError",
    "InvalidCatalogError",
    "InvalidLocaleError",
    "Loader",
    "LocJsonError",
    "Localizer",
    "MissingTranslationError",
    "RawSource",
    "Translator",
    "__version__",
    "direction",
    "for_locale",
    "get_localizer",
    "has",
    "negotiate",
    "scope",
    "set_locale",
    "setup",
    "t",
    "use",
]

_NOT_SET_UP = "call locjson.setup() first"


class _DefaultHolder:
    """Holds the default Localizer, so replacing it is one attribute store."""

    __slots__ = ("localizer",)

    def __init__(self) -> None:
        self.localizer: Localizer | None = None


_DEFAULT = _DefaultHolder()


def setup(
    path: str | os.PathLike[str] | None = None,
    *,
    loader: Loader | None = None,
    default_locale: str = "en",
    fallbacks: Mapping[str, Sequence[str]] | None = None,
    missing: MissingPolicy = "key",
    preload: bool = False,
    strict: bool | None = None,
) -> Localizer:
    """Create a :class:`Localizer` and install it as the module default.

    The arguments are those of :class:`Localizer`. The new Localizer is built
    first and then installed in one step, so calling ``setup()`` again
    replaces the default atomically: a concurrent :func:`t` uses either the
    old or the new one. When construction fails, the previous default stays
    installed.

    Example:
        >>> import locjson  # doctest: +SKIP
        >>> locjson.setup("locales", default_locale="en")  # doctest: +SKIP
        >>> locjson.t("greeting", name="Enes")  # doctest: +SKIP
        'Hello, Enes!'

    Args:
        path: A directory of ``<locale>.json`` files or ``<locale>/``
            directories.
        loader: Any :class:`Loader`, instead of ``path``.
        default_locale: The locale used when none is requested.
        fallbacks: Extra locales to try per locale.
        missing: What :func:`t` does when a key is missing everywhere.
        preload: Load and validate every locale now.
        strict: Make every slip raise. ``None`` reads ``LOCJSON_STRICT``
            once, here.

    Returns:
        The installed Localizer.

    Raises:
        ConfigurationError: If the arguments are invalid (see
            :class:`Localizer`).
        InvalidLocaleError: If a configured locale tag is invalid.
        InvalidCatalogError: If discovery or ``preload`` finds a bad catalog.
    """
    localizer = Localizer(
        path,
        loader=loader,
        default_locale=default_locale,
        fallbacks=fallbacks,
        missing=missing,
        preload=preload,
        strict=strict,
    )
    _DEFAULT.localizer = localizer
    return localizer


def get_localizer() -> Localizer:
    """Return the default Localizer installed by :func:`setup`.

    Returns:
        The default Localizer.

    Raises:
        LocJsonError: If :func:`setup` has not been called.
    """
    localizer = _DEFAULT.localizer
    if localizer is None:
        raise LocJsonError(_NOT_SET_UP)
    return localizer


def t(
    key: str,
    /,
    *,
    locale: str | None = None,
    count: int | float | Decimal | None = None,
    context: None = None,
    **variables: object,
) -> str:
    """Translate ``key`` with the default Localizer (see :meth:`Localizer.t`).

    Args:
        key: A flat dot key such as ``"nav.home"``.
        locale: The locale to translate into. Defaults to the current locale.
        count: The quantity for plural messages, also available as
            ``{count}``.
        context: Reserved for a future version; must be ``None``.
        **variables: Placeholder values.

    Returns:
        The rendered translation, or the result of the ``missing`` policy.

    Raises:
        LocJsonError: If :func:`setup` has not been called, or ``context`` is
            not ``None``.
        MissingTranslationError: If the key is missing and slips raise.
        InterpolationError: If a value is missing and slips raise.
        InvalidCatalogError: If a catalog needed for the lookup is invalid.
    """
    return get_localizer().t(
        key, locale=locale, count=count, context=context, **variables
    )


def has(key: str, /, *, locale: str | None = None) -> bool:
    """Tell whether the default Localizer translates ``key``.

    See :meth:`Localizer.has`.

    Args:
        key: A flat dot key.
        locale: The locale whose chain is searched. Defaults to the current
            locale.

    Returns:
        ``True`` if a translation exists.

    Raises:
        LocJsonError: If :func:`setup` has not been called.
        InvalidCatalogError: If a catalog needed for the lookup is invalid.
    """
    return get_localizer().has(key, locale=locale)


def use(locale: str) -> AbstractContextManager[str]:
    """Use ``locale`` as the default Localizer's locale inside a ``with`` block.

    See :meth:`Localizer.use`.

    Args:
        locale: A locale tag. An invalid tag means the default locale.

    Returns:
        A context manager that yields the canonical locale in effect.

    Raises:
        LocJsonError: If :func:`setup` has not been called.
    """
    return get_localizer().use(locale)


def for_locale(locale: str) -> Translator:
    """Return a :class:`Translator` of the default Localizer bound to ``locale``.

    See :meth:`Localizer.for_locale`.

    Args:
        locale: A locale tag. An invalid tag binds the default locale.

    Returns:
        A Translator that never reads or changes the current locale.

    Raises:
        LocJsonError: If :func:`setup` has not been called.
    """
    return get_localizer().for_locale(locale)


def scope(prefix: str) -> Translator:
    """Return a :class:`Translator` of the default Localizer scoped to ``prefix``.

    See :meth:`Localizer.scope`.

    Args:
        prefix: A key prefix such as ``"inbox"``.

    Returns:
        A Translator that prepends ``prefix`` to every key.

    Raises:
        LocJsonError: If :func:`setup` has not been called.
        ConfigurationError: If ``prefix`` is not a valid prefix.
    """
    return get_localizer().scope(prefix)


def set_locale(locale: str) -> None:
    """Set the default Localizer's locale for the current context.

    See :meth:`Localizer.set_locale`.

    Args:
        locale: A locale tag. An invalid tag clears the current locale.

    Raises:
        LocJsonError: If :func:`setup` has not been called.
    """
    get_localizer().set_locale(locale)
