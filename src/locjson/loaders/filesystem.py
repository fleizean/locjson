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

_Kind = Literal["file", "dir"]


class _Entry:
    """One discovered locale: a ``<tag>.json`` file or a ``<tag>/`` directory."""

    __slots__ = ("kind", "path")

    def __init__(self, kind: _Kind, path: Path) -> None:
        self.kind: _Kind = kind
        self.path = path


class FilesystemLoader:
    """Read locale catalogs from one directory, in either of two layouts.

    The layout is detected per locale from the top level of ``path``:

    - **single file:** ``<path>/<tag>.json`` holds every key of the locale.
    - **namespaced:** each ``<path>/<tag>/<ns>.json`` holds the keys of one
      namespace, which are read as ``<ns>.<key>`` (``tr/common.json`` with
      ``greeting`` serves ``common.greeting``).

    Discovery rules:

    - Only the top level of ``path`` is listed. Names starting with ``.`` are
      ignored, and so are files that do not end in ``.json``. The suffix match
      is exact and case-sensitive, so ``en.JSON`` is ignored too.
    - Every other ``.json`` file and every directory must be named after a
      valid locale tag (``_`` is accepted as a separator). ``common.json``,
      ``root/`` or ``en.UTF-8.json`` raise instead of being skipped.
    - Two entries for one locale raise and name both entries: ``en.json``
      together with ``en/`` (both layouts), or ``pt_BR.json`` together with
      ``pt-BR.json``.
    - Namespaces are one level deep: inside a locale directory, dot entries
      and non-``.json`` files are ignored, a subdirectory raises, and a
      namespace stem must not contain ``.`` or start with ``$``. A locale
      directory with no namespace files is an empty catalog.
    - Entries are visited in sorted order, so errors are the same on every
      operating system. Symbolic links are followed.

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

        Each call rescans the directory and replaces the previous result, so
        a later :meth:`load` sees locales added or removed since.

        Returns:
            Canonical locale tags.

        Raises:
            ConfigurationError: If the catalog directory does not exist or is
                not a directory.
            InvalidCatalogError: If an entry is not named after a valid locale
                tag, or two entries are the same locale.
        """
        if not self._root.exists():
            msg = f"catalog directory does not exist: {self._root}"
            raise ConfigurationError(msg)
        if not self._root.is_dir():
            msg = f"catalog path is not a directory: {self._root}"
            raise ConfigurationError(msg)
        self._entries = self._scan_root()
        return frozenset(self._entries)

    def load(self, locale: str) -> tuple[RawSource, ...]:
        """Read and parse the files of one discovered locale.

        Args:
            locale: A canonical tag returned by :meth:`discover_locales`.

        Returns:
            The parsed documents, sorted by origin. A namespaced locale yields
            one source per ``<ns>.json`` file with ``namespace=<ns>``.

        Raises:
            LocJsonError: If ``locale`` was not discovered.
            InvalidCatalogError: If a file is not UTF-8 or not valid JSON, or
                a locale directory breaks a namespace rule.
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
            for origin, stem, path in self._scan_namespaces(locale, entry.path)
        ]
        return tuple(sorted(sources, key=lambda source: source.origin))

    def _scan_root(self) -> dict[str, _Entry]:
        """Map each locale tag to its entry at the top level of the root."""
        found: dict[str, _Entry] = {}
        shown: dict[str, str] = {}
        for item in _sorted_scan(self._root):
            name = item.name
            if name.startswith("."):
                continue
            kind: _Kind
            if item.is_dir():
                kind, stem, label = "dir", name, name + "/"
            elif item.is_file() and name.endswith(_SUFFIX):
                kind, stem, label = "file", name[: -len(_SUFFIX)], name
            else:
                continue
            tag = _tag_of(stem)
            if tag is None:
                raise InvalidCatalogError(
                    f"'{label}' is not named after a valid locale tag", path=label
                )
            previous = found.get(tag)
            if previous is not None:
                if previous.kind == kind:
                    problem = (
                        f"'{label}' and '{shown[tag]}' are the same locale '{tag}'"
                    )
                else:
                    problem = f"locale '{tag}' is present in both layouts"
                raise InvalidCatalogError(
                    problem, path=label, locale=tag, other_path=shown[tag]
                )
            found[tag] = _Entry(kind, Path(item.path))
            shown[tag] = label
        return found

    @staticmethod
    def _scan_namespaces(tag: str, directory: Path) -> list[tuple[str, str, Path]]:
        """List ``(origin, namespace, path)`` for the namespace files of a locale."""
        found: list[tuple[str, str, Path]] = []
        for item in _sorted_scan(directory):
            name = item.name
            if name.startswith("."):
                continue
            origin = f"{directory.name}/{name}"
            if item.is_dir():
                raise InvalidCatalogError(
                    f"namespaces are one level deep; '{origin}/' is a directory",
                    path=origin + "/",
                    locale=tag,
                )
            if not (item.is_file() and name.endswith(_SUFFIX)):
                continue
            stem = name[: -len(_SUFFIX)]
            if "." in stem or stem.startswith("$"):
                raise InvalidCatalogError(
                    f"namespace '{stem}' must not contain '.' or start with '$'",
                    path=origin,
                    locale=tag,
                )
            found.append((origin, stem, Path(item.path)))
        return found


def _sorted_scan(directory: Path) -> list[os.DirEntry[str]]:
    """List a directory once, sorted by name for deterministic errors."""
    with os.scandir(directory) as scan:
        return sorted(scan, key=lambda item: item.name)


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
