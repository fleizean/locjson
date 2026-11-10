"""Load catalogs from a directory of JSON locale files."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from locjson._compat import override
from locjson._jsonio import read_json
from locjson.errors import (
    ConfigurationError,
    InvalidCatalogError,
    InvalidLocaleError,
    LocJsonError,
)
from locjson.loaders.base import RawSource
from locjson.locale import normalize

if TYPE_CHECKING:
    import os

__all__ = ["FilesystemLoader"]

_SUFFIX = ".json"


class FilesystemLoader:
    """Read ``<tag>.json`` files from the top level of one directory.

    Discovery only lists the directory. Files are read when a locale is first
    loaded, and only files found by the latest discovery are ever opened: a
    requested locale tag is never turned into a path.

    Args:
        path: The catalog directory.
    """

    __slots__ = ("_files", "_root")

    def __init__(self, path: str | os.PathLike[str]) -> None:
        self._root = Path(path)
        self._files: dict[str, tuple[tuple[str, Path], ...]] = {}

    @override
    def __repr__(self) -> str:
        return f"FilesystemLoader({str(self._root)!r})"

    @property
    def root(self) -> Path:
        """The catalog directory."""
        return self._root

    def discover_locales(self) -> frozenset[str]:
        """List the locales found at the top level of the catalog directory.

        Dotfiles, non-``.json`` files and directories are ignored.

        Returns:
            Canonical locale tags.

        Raises:
            ConfigurationError: If the catalog directory does not exist.
            InvalidCatalogError: If a ``.json`` file name is not a valid locale
                tag, or two file names normalize to the same locale.
        """
        if not self._root.is_dir():
            msg = f"catalog directory does not exist: {self._root}"
            raise ConfigurationError(msg)
        found: dict[str, tuple[tuple[str, Path], ...]] = {}
        for entry in sorted(self._root.iterdir(), key=lambda item: item.name):
            name = entry.name
            if name.startswith(".") or not name.endswith(_SUFFIX):
                continue
            if not entry.is_file():
                continue
            try:
                tag = normalize(name[: -len(_SUFFIX)])
            except InvalidLocaleError:
                raise InvalidCatalogError(
                    "file name is not a valid locale tag", path=name
                ) from None
            if tag in found:
                raise InvalidCatalogError(
                    f"file name collides with another file for locale {tag!r}",
                    path=name,
                    locale=tag,
                    other_path=found[tag][0][0],
                )
            found[tag] = ((name, entry),)
        self._files = found
        return frozenset(found)

    def load(self, locale: str) -> tuple[RawSource, ...]:
        """Read and parse the files of one discovered locale.

        Args:
            locale: A canonical tag returned by :meth:`discover_locales`.

        Returns:
            The parsed documents, sorted by origin.

        Raises:
            LocJsonError: If ``locale`` was not discovered.
            InvalidCatalogError: If a file is not UTF-8 or not valid JSON.
        """
        files = self._files.get(locale)
        if files is None:
            msg = f"locale {locale!r} was not discovered in {self._root}"
            raise LocJsonError(msg)
        sources = [
            RawSource(read_json(path.read_bytes(), origin=origin), origin)
            for origin, path in files
        ]
        return tuple(sorted(sources, key=lambda source: source.origin))
