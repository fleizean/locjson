"""The catalog validator :func:`build_catalog` and the immutable :class:`Catalog`.

``build_catalog`` is the single place where raw documents become a catalog.
The runtime and the CLI share it, so both apply exactly the same rules.
"""

from __future__ import annotations

import collections
import re
from collections.abc import Mapping
from typing import TYPE_CHECKING, TypeVar, overload

from locjson._compat import override
from locjson._jsonio import JsonObject, NonFinite, escape_pointer_token
from locjson.errors import CatalogIssue, InvalidCatalogError
from locjson.formatting import Template, TemplateError, compile_template

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence
    from typing import NamedTuple

    from locjson.loaders.base import RawSource

    class _BuildResultFields(NamedTuple):
        catalog: Catalog | None
        issues: tuple[CatalogIssue, ...]

else:
    # Functional form: class-syntax typing.NamedTuple imports ast on 3.14 (PKG-03).
    _BuildResultFields = collections.namedtuple(
        "_BuildResultFields", ["catalog", "issues"]
    )

__all__ = ["MAX_DEPTH", "BuildResult", "Catalog", "Meta", "build_catalog"]

MAX_DEPTH = 32
"""Deepest allowed object nesting in a catalog file; the top level is level 1."""

_T = TypeVar("_T")
_SURROGATE = re.compile("[\ud800-\udfff]")


class Meta:
    """Per-locale metadata from ``$meta``.

    Attributes:
        locale: The locale declared by ``$meta.locale``, or ``None``.
        direction: ``"ltr"``, ``"rtl"`` or ``None`` when not declared.
    """

    __slots__ = ("_direction", "_locale")

    _direction: str | None
    _locale: str | None

    def __init__(self, locale: str | None = None, direction: str | None = None) -> None:
        object.__setattr__(self, "_locale", locale)
        object.__setattr__(self, "_direction", direction)

    @override
    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError(f"{type(self).__name__} is immutable")

    @override
    def __repr__(self) -> str:
        return f"Meta(locale={self._locale!r}, direction={self._direction!r})"

    @property
    def locale(self) -> str | None:
        """The locale declared by ``$meta.locale``, or ``None``."""
        return self._locale

    @property
    def direction(self) -> str | None:
        """The text direction declared by ``$meta.direction``, or ``None``."""
        return self._direction


class Catalog(Mapping[str, Template]):
    """An immutable, validated catalog for one locale.

    It maps flat dot keys such as ``"nav.home"`` to compiled templates.
    """

    __slots__ = ("_entries", "_locale", "_meta")

    _entries: dict[str, Template]
    _locale: str
    _meta: Meta

    def __init__(
        self, locale: str, entries: Mapping[str, Template], meta: Meta | None = None
    ) -> None:
        object.__setattr__(self, "_locale", locale)
        object.__setattr__(self, "_entries", dict(entries))
        object.__setattr__(self, "_meta", meta if meta is not None else Meta())

    @override
    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError(f"{type(self).__name__} is immutable")

    @override
    def __repr__(self) -> str:
        return f"Catalog(locale={self._locale!r}, keys={len(self._entries)})"

    @override
    def __getitem__(self, key: str) -> Template:
        return self._entries[key]

    @override
    def __iter__(self) -> Iterator[str]:
        return iter(self._entries)

    @override
    def __len__(self) -> int:
        return len(self._entries)

    @override
    def __contains__(self, key: object) -> bool:
        return key in self._entries

    @overload
    def get(self, key: str, /) -> Template | None: ...
    @overload
    def get(self, key: str, default: Template, /) -> Template: ...
    @overload
    def get(self, key: str, default: _T, /) -> Template | _T: ...
    @override
    def get(self, key: str, default: object = None, /) -> object:
        """Return the template for ``key``, or ``default`` when absent.

        Args:
            key: A flat dot key.
            default: The value returned when ``key`` is absent.

        Returns:
            The template or ``default``.
        """
        return self._entries.get(key, default)

    @property
    def locale(self) -> str:
        """The canonical locale this catalog belongs to."""
        return self._locale

    @property
    def meta(self) -> Meta:
        """The locale's ``$meta`` values."""
        return self._meta

    @property
    def direction(self) -> str | None:
        """The declared text direction (``"ltr"``/``"rtl"``), or ``None``."""
        return self._meta.direction


class BuildResult(_BuildResultFields):
    """The outcome of :func:`build_catalog` (a ``NamedTuple``).

    Attributes:
        catalog: The catalog, or ``None`` when any issue was found.
        issues: Every issue found, sorted by ``(path, pointer, problem)``.
    """

    __slots__ = ()

    def unwrap(self) -> Catalog:
        """Return the catalog or raise for its issues.

        Returns:
            The catalog.

        Raises:
            InvalidCatalogError: If any issue was found. It reports the first
                issue and keeps all of them in ``.issues``.
        """
        if self.issues or self.catalog is None:
            raise InvalidCatalogError.from_issues(self.issues)
        return self.catalog


def build_catalog(locale: str, sources: Sequence[RawSource]) -> BuildResult:
    """Validate raw documents and compile them into one catalog.

    Nested objects become dot keys (``{"nav": {"home": ...}}`` gives
    ``"nav.home"``). Empty strings and ``null`` mean "untranslated" and are not
    stored. Keys starting with ``$`` are reserved and never become
    translations. Every string is compiled once, here, so lookups never parse
    text.

    This function is pure and never raises for catalog content: problems are
    collected as issues with RFC 6901 pointers.

    Args:
        locale: The canonical locale the documents belong to.
        sources: The locale's documents.

    Returns:
        The catalog, or ``None`` with every issue found.
    """
    builder = _Builder(locale)
    for source in sources:
        data = source.data
        if not isinstance(data, Mapping):
            problem = f"expected a JSON object at the top level, got {_kind(data)}"
            builder.issue(source.origin, "", problem)
            continue
        prefix = source.namespace + "." if source.namespace else ""
        builder.walk(data, prefix, "", source.origin)
    if builder.issues:
        issues = sorted(
            builder.issues, key=lambda issue: (issue.path, issue.pointer, issue.problem)
        )
        return BuildResult(None, tuple(issues))
    return BuildResult(Catalog(locale, builder.entries), ())


class _Builder:
    """Mutable state of one :func:`build_catalog` run."""

    __slots__ = ("entries", "issues", "locale")

    def __init__(self, locale: str) -> None:
        self.locale = locale
        self.entries: dict[str, Template] = {}
        self.issues: list[CatalogIssue] = []

    def issue(self, origin: str, pointer: str, problem: str) -> None:
        self.issues.append(CatalogIssue(origin, pointer, problem, self.locale))

    def walk(
        self,
        node: Mapping[object, object],
        prefix: str,
        pointer: str,
        origin: str,
        depth: int = 1,
    ) -> None:
        if isinstance(node, JsonObject):
            for duplicate in dict.fromkeys(node.duplicates):
                child = f"{pointer}/{_token(duplicate)}"
                self.issue(origin, child, f"duplicate key '{_safe(duplicate)}'")
        for raw_key, value in node.items():
            if not isinstance(raw_key, str):
                token = escape_pointer_token(str(raw_key))
                problem = f"object keys must be strings, got {_kind(raw_key)}"
                self.issue(origin, f"{pointer}/{token}", problem)
                continue
            child = f"{pointer}/{_token(raw_key)}"
            if _SURROGATE.search(raw_key):
                self.issue(origin, child, "lone surrogate in key")
                continue
            if raw_key.startswith("$"):
                continue
            key = prefix + raw_key
            if not isinstance(value, Mapping):
                self.leaf(key, value, child, origin)
            elif depth >= MAX_DEPTH:
                problem = f"nesting deeper than {MAX_DEPTH} levels"
                self.issue(origin, child, problem)
            else:
                self.walk(value, key + ".", child, origin, depth + 1)

    def leaf(self, key: str, value: object, pointer: str, origin: str) -> None:
        if isinstance(value, str):
            if not value:
                return
            if _SURROGATE.search(value):
                self.issue(origin, pointer, "lone surrogate in value")
                return
            try:
                self.entries[key] = compile_template(value)
            except TemplateError as exc:
                self.issue(origin, pointer, str(exc))
        elif isinstance(value, NonFinite):
            self.issue(origin, pointer, f"{value.name} is not valid JSON")
        elif value is not None:
            problem = f"expected a string or object, got {_kind(value)}"
            self.issue(origin, pointer, problem)


def _kind(value: object) -> str:
    return type(value).__name__


def _safe(text: str) -> str:
    r"""Return ``text`` with lone surrogates written as backslash escapes.

    Diagnostics must stay encodable as UTF-8 even when they name a key that
    holds a lone surrogate, so U+D800 is shown as the six characters
    ``\ud800``.
    """
    if _SURROGATE.search(text):
        return text.encode("utf-8", "backslashreplace").decode("utf-8")
    return text


def _token(key: str) -> str:
    return escape_pointer_token(_safe(key))
