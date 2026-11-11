"""The :class:`Loader` protocol and the :class:`RawSource` it produces."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

from locjson._compat import override

if TYPE_CHECKING:
    from collections.abc import Sequence

__all__ = ["Loader", "RawSource"]


class RawSource:
    """One decoded catalog document, before validation.

    A :class:`Loader` returns these from :meth:`Loader.load`. The data is
    already decoded: a loader for another format (YAML, TOML, a database)
    parses its own input and hands over plain Python values. Every source then
    goes through the same validator as a JSON file, so a loader cannot bypass
    the catalog rules.

    Args:
        data: The decoded document. A valid catalog is a mapping of string
            keys to strings, nested mappings, plural entries or ``None``.
        origin: Where the document came from, shown in every diagnostic.
        namespace: Key prefix for the document, or ``None``.

    Attributes:
        data: The decoded document (a JSON object for valid catalogs).
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
    """A source of catalog documents: the extension point for custom storage.

    :class:`~locjson.Localizer` depends only on this protocol, so catalogs can
    come from the filesystem (:class:`~locjson.FilesystemLoader`), from memory
    (:class:`~locjson.DictLoader`) or from any custom store. A custom loader
    does not need to inherit from this class: any object with these two
    methods qualifies, and ``isinstance(obj, Loader)`` checks for them.

    The contract:

    - :meth:`discover_locales` is cheap and returns canonical tags (see
      :func:`~locjson.locale.normalize`). It is called when the
      :class:`~locjson.Localizer` is created.
    - :meth:`load` is called when a locale is first needed, and only with a
      tag from the latest discovery. It returns decoded documents as
      :class:`RawSource`
      objects sorted by ``origin``. Formats other than JSON decode their
      input here.
    - All returned data is validated by the same rules as JSON files, and
      problems are reported against each source's ``origin``.

    Example:
        A loader for documents kept in a tuple::

            class TupleLoader:
                def __init__(self, pairs):
                    self.pairs = pairs

                def discover_locales(self):
                    return frozenset(tag for tag, _ in self.pairs)

                def load(self, locale):
                    return tuple(
                        RawSource(data, f"<tuple>/{tag}")
                        for tag, data in self.pairs
                        if tag == locale
                    )


            Localizer(loader=TupleLoader((("en", {"hi": "Hello"}),)))
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
