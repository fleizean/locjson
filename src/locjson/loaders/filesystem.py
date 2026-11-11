"""Load catalogs from a directory of JSON locale files."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

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

__all__ = ["FilesystemLoader"]

_SUFFIX = ".json"


class _Entry:
    """One discovered locale: a ``<tag>.json`` file or a ``<tag>/`` directory."""

    __slots__ = ("kind", "path")

    def __init__(self, kind: Literal["file", "dir"], path: Path) -> None:
        self.kind: Literal["file", "dir"] = kind
        self.path = path


class FilesystemLoader:
    """Read locale catalogs from the top level of one directory.

    Two layouts are detected per locale:

    - single file: ``<root>/<tag>.json`` holds every key of the locale;
    - namespaced: ``<root>/<tag>/<ns>.json`` files each hold the keys of one
      namespace, which become ``<ns>.<key>``.

    Discovery only lists the directory. Files are read when a locale is first
    loaded, and only entries found by the latest discovery are ever opened: a
    requested locale tag is never turned into a path.

    Args:
        path: The catalog directory.
    """

    __slots__ = ("_entries", "_root")

    def __init__(self, path: str | os.PathLike[str]) -> None:
        self._root = Path(path)
        self._entries: dict[str, _Entry] = {}

    @override
    def __repr__(self) -> str:
        return f"FilesystemLoader({str(self._root)!r})"

    @property
    def root(self) -> Path:
        """The catalog directory."""
        return self._root

    def discover_locales(self) -> frozenset[str]:
        """List the locales found at the top level of the catalog directory.

        Dotfiles and non-``.json`` files are ignored.

        Returns:
            Canonical locale tags.

        Raises:
            ConfigurationError: If the catalog directory does not exist.
            InvalidCatalogError: If a ``.json`` file name is not a valid locale
                tag, or two entries normalize to the same locale.
        """
        if not self._root.is_dir():
            msg = f"catalog directory does not exist: {self._root}"
            raise ConfigurationError(msg)
        self._entries = self._scan_root()
        return frozenset(self._entries)

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
        entry = self._entries.get(locale)
        if entry is None:
            msg = f"locale {locale!r} was not discovered in {self._root}"
            raise LocJsonError(msg)
        if entry.kind == "file":
            origin = entry.path.name
            return (
                RawSource(read_json(entry.path.read_bytes(), origin=origin), origin),
            )
        sources = [
            RawSource(
                read_json(path.read_bytes(), origin=origin), origin, namespace=stem
            )
            for origin, stem, path in self._scan_namespaces(entry.path)
        ]
        return tuple(sorted(sources, key=lambda source: source.origin))

    def _scan_root(self) -> dict[str, _Entry]:
        found: dict[str, _Entry] = {}
        names: dict[str, str] = {}
        with os.scandir(self._root) as scan:
            items = sorted(scan, key=lambda item: item.name)
        for item in items:
            name = item.name
            if name.startswith("."):
                continue
            if item.is_dir():
                kind: Literal["file", "dir"] = "dir"
                stem = name
                shown = name + "/"
            elif item.is_file() and name.endswith(_SUFFIX):
                kind = "file"
                stem = name[: -len(_SUFFIX)]
                shown = name
            else:
                continue
            tag = _tag_of(stem)
            if tag is None:
                if kind == "dir":
                    continue
                raise InvalidCatalogError(
                    "file name is not a valid locale tag", path=name
                )
            if tag in found:
                raise InvalidCatalogError(
                    f"file name collides with another file for locale {tag!r}",
                    path=shown,
                    locale=tag,
                    other_path=names[tag],
                )
            found[tag] = _Entry(kind, Path(item.path))
            names[tag] = shown
        return found

    def _scan_namespaces(self, directory: Path) -> list[tuple[str, str, Path]]:
        found: list[tuple[str, str, Path]] = []
        with os.scandir(directory) as scan:
            items = sorted(scan, key=lambda item: item.name)
        for item in items:
            name = item.name
            if name.startswith(".") or not name.endswith(_SUFFIX):
                continue
            if not item.is_file():
                continue
            origin = f"{directory.name}/{name}"
            found.append((origin, name[: -len(_SUFFIX)], Path(item.path)))
        return found


def _tag_of(stem: str) -> str | None:
    """Return the canonical tag a file or directory is named after, or ``None``.

    :func:`~locjson.locale.normalize` strips a POSIX ``.codeset`` and
    ``@modifier``, which is right for request-time tags but would let names
    such as ``tr.json/`` or ``en.UTF-8.json`` pass as ``tr`` and ``en``.
    """
    if "." in stem or "@" in stem:
        return None
    try:
        return normalize(stem)
    except InvalidLocaleError:
        return None
