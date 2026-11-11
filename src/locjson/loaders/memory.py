"""Serve catalogs from in-memory mappings."""

from __future__ import annotations

from typing import TYPE_CHECKING

from locjson._compat import override
from locjson.errors import InvalidCatalogError, InvalidLocaleError, LocJsonError
from locjson.loaders.base import RawSource
from locjson.locale import normalize

if TYPE_CHECKING:
    from collections.abc import Mapping

__all__ = ["DictLoader"]


class DictLoader:
    """Serve catalogs from a mapping of locale tag to catalog document.

    Each value has the same shape as one ``<tag>.json`` file and goes through
    the same validation, so ``Localizer(loader=DictLoader(data))`` behaves like
    a directory holding the same content in the single-file layout. Use it for
    tests, for catalogs built at runtime, or as a model for a custom
    :class:`~locjson.Loader`.

    Keys are normalized when the loader is created: ``"en_us"`` is served as
    ``"en-US"``. Each locale yields one source whose origin is
    ``"<dict>/<tag>"`` and which has no namespace.

    The mappings are read when a locale is first loaded, not copied here:
    do not mutate them after creating the loader.

    Args:
        catalogs: Catalog documents by locale tag. Tags are normalized, so
            ``"pt_BR"`` serves ``"pt-BR"``.

    Raises:
        InvalidCatalogError: If a key is not a valid locale tag, or two keys
            normalize to the same locale (``"pt_BR"`` and ``"pt-BR"``).
    """

    __slots__ = ("_catalogs",)

    def __init__(self, catalogs: Mapping[str, Mapping[str, object]]) -> None:
        found: dict[str, Mapping[str, object]] = {}
        origins: dict[str, str] = {}
        for key, data in catalogs.items():
            origin = _origin(key)
            try:
                tag = normalize(key)
            except InvalidLocaleError:
                raise InvalidCatalogError(
                    "catalog key is not a valid locale tag", path=origin
                ) from None
            if tag in found:
                raise InvalidCatalogError(
                    f"catalog key collides with another key for locale {tag!r}",
                    path=origin,
                    locale=tag,
                    other_path=origins[tag],
                )
            found[tag] = data
            origins[tag] = origin
        self._catalogs = found

    @override
    def __repr__(self) -> str:
        return f"DictLoader(locales={sorted(self._catalogs)!r})"

    def discover_locales(self) -> frozenset[str]:
        """List the locales held by this loader.

        Returns:
            Canonical locale tags.
        """
        return frozenset(self._catalogs)

    def load(self, locale: str) -> tuple[RawSource, ...]:
        """Return the document of one locale.

        Args:
            locale: A canonical tag returned by :meth:`discover_locales`.

        Returns:
            One source whose origin is ``"<dict>/<tag>"``.

        Raises:
            LocJsonError: If the loader holds no catalog for ``locale``.
        """
        if locale not in self._catalogs:
            msg = f"locale {locale!r} is not held by this DictLoader"
            raise LocJsonError(msg)
        return (RawSource(self._catalogs[locale], "<dict>/" + locale),)


def _origin(key: object) -> str:
    return "<dict>/" + (key if isinstance(key, str) else repr(key))
