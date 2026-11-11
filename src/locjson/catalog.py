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
from locjson.errors import CatalogIssue, InvalidCatalogError, InvalidLocaleError
from locjson.formatting import Template, TemplateError, compile_template
from locjson.locale import normalize

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
_DIRECTIONS = ("ltr", "rtl")
_RESERVED = frozenset({"$meta", "$plural"})


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

    The rules, which freeze the catalog file format:

    - Each document's top level must be a JSON object. Nested objects become
      dot keys (``{"nav": {"home": ...}}`` gives ``"nav.home"``), and a
      literal key may contain dots itself (``{"nav.home": ...}``). Key
      segments must not be empty, and only the first segment of a literal key
      may start with ``$``. A namespaced source prefixes its keys with
      ``<namespace>.``.
    - Keys starting with ``$`` are reserved and never become translations.
      ``$meta`` is allowed only at the top level of a file and may hold only
      ``locale`` (equal to ``locale`` after normalization) and ``direction``
      (``"ltr"`` or ``"rtl"``); values are merged across the locale's sources
      and must agree. ``$plural`` accepts only ``false``. Every other ``$`` key
      is an annotation (``$comment``) and is skipped, value included.
    - Leaves must be strings or ``null``. ``""`` and ``null`` mean
      "untranslated" and are not stored, so lookups fall through to the next
      locale. Every other string is compiled once, here, so lookups never
      parse text. Keys and values are kept exactly as decoded, with no
      Unicode normalization.
    - The same flat key may not be defined twice, and a translation may not
      also be the prefix of another key (``a.b`` and ``a.b.c``). Both
      locations are named in the issue.
    - Duplicate JSON keys, ``NaN``/``Infinity``, lone surrogates and objects
      nested deeper than :data:`MAX_DEPTH` levels are errors.

    This function is pure and never raises for catalog content: problems are
    collected as issues with RFC 6901 pointers. The result does not depend on
    the order of ``sources`` or of keys within them.

    Args:
        locale: The canonical locale the documents belong to.
        sources: The locale's documents.

    Returns:
        The catalog and no issues, or ``None`` and every issue found, sorted by
        ``(path, pointer, problem)``. A partial catalog is never returned.
    """
    builder = _Builder(locale)
    for source in sorted(sources, key=lambda source: source.origin):
        builder.add(source)
    builder.check_keys()
    if builder.issues:
        issues = sorted(
            builder.issues, key=lambda issue: (issue.path, issue.pointer, issue.problem)
        )
        return BuildResult(None, tuple(issues))
    return BuildResult(Catalog(locale, builder.entries, builder.merged_meta()), ())


class _Builder:
    """Mutable state of one :func:`build_catalog` run."""

    __slots__ = ("entries", "groups", "issues", "locale", "meta", "places")

    def __init__(self, locale: str) -> None:
        self.locale = locale
        self.entries: dict[str, Template] = {}
        self.issues: list[CatalogIssue] = []
        # Flat key -> every (origin, pointer) that defines it, for collisions.
        self.places: dict[str, list[tuple[str, str]]] = {}
        # $meta field -> (value, origin, pointer) of its first declaration.
        self.meta: dict[str, tuple[str, str, str]] = {}
        # Flat prefixes of objects marked "$plural": false (plural detection).
        self.groups: set[str] = set()

    def issue(
        self,
        origin: str,
        pointer: str,
        problem: str,
        other: tuple[str, str] | None = None,
    ) -> None:
        other_path, other_pointer = other if other is not None else (None, None)
        self.issues.append(
            CatalogIssue(
                origin, pointer, problem, self.locale, other_path, other_pointer
            )
        )

    def add(self, source: RawSource) -> None:
        data = source.data
        if not isinstance(data, Mapping):
            problem = f"expected a JSON object at the top level, got {_kind(data)}"
            self.issue(source.origin, "", problem)
            return
        prefix = source.namespace + "." if source.namespace else ""
        self.walk(data, prefix, "", source.origin, 1)

    def merged_meta(self) -> Meta:
        locale = self.meta.get("locale")
        direction = self.meta.get("direction")
        return Meta(
            locale[0] if locale is not None else None,
            direction[0] if direction is not None else None,
        )

    def duplicates(
        self, node: Mapping[object, object], pointer: str, origin: str
    ) -> None:
        if not isinstance(node, JsonObject):
            return
        for key in dict.fromkeys(node.duplicates):
            if key.startswith("$") and key not in _RESERVED:
                continue  # repeated annotations such as "$comment" are fine
            child = f"{pointer}/{_token(key)}"
            self.issue(origin, child, f"duplicate key '{_safe(key)}'")

    def walk(
        self,
        node: Mapping[object, object],
        prefix: str,
        pointer: str,
        origin: str,
        depth: int,
    ) -> None:
        self.duplicates(node, pointer, origin)
        for raw_key, value in node.items():
            if not isinstance(raw_key, str):
                token = escape_pointer_token(str(raw_key))
                problem = f"object keys must be strings, got {_kind(raw_key)}"
                self.issue(origin, f"{pointer}/{token}", problem)
                continue
            child = f"{pointer}/{_token(raw_key)}"
            if _SURROGATE.search(raw_key):
                self.issue(origin, child, "lone surrogate in key")
            elif raw_key.startswith("$"):
                self.reserved(raw_key, value, prefix, child, origin, top=depth == 1)
            elif self.valid_key(raw_key, child, origin):
                self.node(prefix + raw_key, value, child, origin, depth)

    def node(
        self, key: str, value: object, pointer: str, origin: str, depth: int
    ) -> None:
        if not isinstance(value, Mapping):
            self.places.setdefault(key, []).append((origin, pointer))
            self.leaf(key, value, pointer, origin)
        elif depth >= MAX_DEPTH:
            problem = f"nesting deeper than {MAX_DEPTH} levels"
            self.issue(origin, pointer, problem)
        else:
            self.walk(value, key + ".", pointer, origin, depth + 1)

    def valid_key(self, key: str, pointer: str, origin: str) -> bool:
        segments = key.split(".")
        if "" in segments:
            self.issue(origin, pointer, f"empty key segment in key '{key}'")
            return False
        for segment in segments[1:]:
            if segment.startswith("$"):
                problem = (
                    f"key segment '{segment}' in key '{key}' starts with '$', "
                    "which is reserved"
                )
                self.issue(origin, pointer, problem)
                return False
        return True

    def reserved(
        self,
        key: str,
        value: object,
        prefix: str,
        pointer: str,
        origin: str,
        *,
        top: bool,
    ) -> None:
        if key == "$meta":
            if top:
                self.read_meta(value, pointer, origin)
            else:
                problem = "$meta is only allowed at the top level of a file"
                self.issue(origin, pointer, problem)
        elif key == "$plural":
            if value is False:
                self.groups.add(prefix[:-1])
            else:
                self.issue(origin, pointer, "$plural only accepts false")
        # Any other "$" key is an annotation: skipped, value not validated.

    def read_meta(self, meta: object, pointer: str, origin: str) -> None:
        if not isinstance(meta, Mapping):
            self.issue(origin, pointer, f"$meta must be an object, got {_kind(meta)}")
            return
        self.duplicates(meta, pointer, origin)
        for field, value in meta.items():
            child = f"{pointer}/{_token(str(field))}"
            if field == "locale":
                checked = self.meta_locale(value, child, origin)
            elif field == "direction":
                checked = self.meta_direction(value, child, origin)
            else:
                problem = (
                    f"unknown $meta key '{_safe(str(field))}'; "
                    "only 'locale' and 'direction' are allowed"
                )
                self.issue(origin, child, problem)
                continue
            if checked is not None:
                self.merge_meta(str(field), checked, child, origin)

    def meta_locale(self, value: object, pointer: str, origin: str) -> str | None:
        if not isinstance(value, str):
            problem = f"$meta.locale must be a string, got {_kind(value)}"
            self.issue(origin, pointer, problem)
            return None
        try:
            tag = normalize(value)
        except InvalidLocaleError:
            self.issue(origin, pointer, "$meta.locale is not a valid locale tag")
            return None
        if tag != self.locale:
            problem = f"$meta.locale does not match the file's locale '{self.locale}'"
            self.issue(origin, pointer, problem)
            return None
        return tag

    def meta_direction(self, value: object, pointer: str, origin: str) -> str | None:
        if isinstance(value, str) and value in _DIRECTIONS:
            return value
        self.issue(origin, pointer, "$meta.direction must be 'ltr' or 'rtl'")
        return None

    def merge_meta(self, field: str, value: str, pointer: str, origin: str) -> None:
        first = self.meta.setdefault(field, (value, origin, pointer))
        if first[0] != value:
            problem = f"$meta.{field} '{value}' conflicts with '{first[0]}'"
            self.issue(origin, pointer, problem, (first[1], first[2]))

    def check_keys(self) -> None:
        places = self.places
        for key, found in places.items():
            first, *others = sorted(found)
            for origin, pointer in others:
                problem = f"key '{key}' is defined more than once"
                self.issue(origin, pointer, problem, first)
            dot = key.find(".")
            while dot != -1:
                parent = key[:dot]
                if parent in places:
                    origin, pointer = first
                    problem = (
                        f"key '{key}' is nested under '{parent}', "
                        "which is a translation"
                    )
                    self.issue(origin, pointer, problem, min(places[parent]))
                dot = key.find(".", dot + 1)

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
