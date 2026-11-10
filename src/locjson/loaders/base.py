"""The :class:`Loader` protocol and the :class:`RawSource` it produces."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

from locjson._compat import override

if TYPE_CHECKING:
    from collections.abc import Sequence

__all__ = ["Loader", "RawSource"]


class RawSource:
    """One parsed catalog document, before validation.

    Attributes:
        data: The parsed document (a JSON object for valid catalogs).
        origin: POSIX-style path relative to the catalog root, such as
            ``"en.json"`` or ``"pt-BR/common.json"``, or ``"<dict>/<tag>"`` for
            in-memory catalogs. Used in every diagnostic.
        namespace: Key prefix for namespaced files (``"common"`` turns
            ``greeting`` into ``common.greeting``), or ``None``.
    """

    __slots__ = ("_data", "_namespace", "_origin")

    _data: object
    _namespace: str | None
    _origin: str

    def __init__(self, data: object, origin: str, namespace: str | None = None) -> None:
        object.__setattr__(self, "_data", data)
        object.__setattr__(self, "_origin", origin)
        object.__setattr__(self, "_namespace", namespace)

    @override
    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError(f"{type(self).__name__} is immutable")

    @override
    def __repr__(self) -> str:
        return f"RawSource(origin={self._origin!r}, namespace={self._namespace!r})"

    @property
    def data(self) -> object:
        """The parsed document."""
        return self._data

    @property
    def origin(self) -> str:
        """The document's path relative to the catalog root."""
        return self._origin

    @property
    def namespace(self) -> str | None:
        """The key prefix for the document's keys, or ``None``."""
        return self._namespace


@runtime_checkable
class Loader(Protocol):
    """A source of catalog documents.

    :class:`~locjson.Localizer` depends only on this protocol, so catalogs can
    come from the filesystem, from memory or from any custom store.
    """

    def discover_locales(self) -> frozenset[str]:
        """List the locales this loader can provide.

        Returns:
            Canonical locale tags. Discovery should be cheap: no catalog
            content needs to be read.
        """
        ...

    def load(self, locale: str) -> Sequence[RawSource]:
        """Read every document for one locale.

        Only called with tags returned by the latest :meth:`discover_locales`.

        Args:
            locale: A canonical locale tag.

        Returns:
            The locale's documents, sorted by ``origin``.
        """
        ...
