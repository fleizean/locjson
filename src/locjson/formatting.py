"""Load-time template compiler and segment renderer.

Catalog text is compiled once, when a catalog is built, into alternating
literal and field segments. Rendering only joins those segments: catalog text
is never passed to ``str.format``, so attribute access, indexing, conversions
and format specs cannot be reached from a translation file.
"""

from __future__ import annotations

import re
import string
from typing import TYPE_CHECKING

from locjson import _log
from locjson._compat import override
from locjson.errors import InterpolationError

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

__all__ = ["Template", "TemplateError", "compile_template"]

_FORMATTER = string.Formatter()
_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_POSITIONAL = re.compile(r"[0-9]*")
_MISSING = object()
_LITERAL_HINT = "use '{{' and '}}' for literal braces"


class TemplateError(ValueError):
    """Raised by :func:`compile_template` for invalid template text (internal)."""


class Template:
    """A compiled, immutable message template.

    ``segments`` alternates literal text and placeholder names, starting and
    ending with a literal, so its length is always odd.
    """

    __slots__ = ("_fields", "_segments", "_source")

    _fields: frozenset[str]
    _segments: tuple[str, ...]
    _source: str

    def __init__(
        self, source: str, segments: tuple[str, ...], fields: frozenset[str]
    ) -> None:
        object.__setattr__(self, "_source", source)
        object.__setattr__(self, "_segments", segments)
        object.__setattr__(self, "_fields", fields)

    @override
    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError(f"{type(self).__name__} is immutable")

    @override
    def __repr__(self) -> str:
        return f"Template({self._source!r})"

    @override
    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Template):
            return NotImplemented
        return self._source == other._source

    @override
    def __hash__(self) -> int:
        return hash(self._source)

    @property
    def source(self) -> str:
        """The template text exactly as it appeared in the catalog."""
        return self._source

    @property
    def fields(self) -> frozenset[str]:
        """The placeholder names the template uses."""
        return self._fields

    @property
    def segments(self) -> tuple[str, ...]:
        """Literal and placeholder segments, alternating, literal first."""
        return self._segments

    def render(
        self,
        values: Mapping[str, object],
        *,
        strict: bool = False,
        key: str = "",
        locale: str = "",
        on_missing: Callable[[str, str, str], None] | None = None,
    ) -> str:
        """Fill the placeholders from ``values``.

        Each present value is inserted as ``str(value)`` and is never parsed
        again, so a value containing braces stays literal. A placeholder with no
        value is kept as the literal text ``{name}`` and reported: to
        ``on_missing(key, locale, name)`` when given, otherwise as a DEBUG
        record on ``locjson`` that names the placeholder and ``key``, never a
        value.

        Args:
            values: Placeholder values by name.
            strict: Raise instead of keeping a placeholder without a value.
            key: The translation key, used in reports and errors.
            locale: The locale of the lookup, passed to ``on_missing``.
            on_missing: Called once per placeholder without a value.

        Returns:
            The rendered text.

        Raises:
            InterpolationError: If ``strict`` is true and a placeholder has no
                value.
        """
        segments = self._segments
        if len(segments) == 1:
            return segments[0]
        parts = [segments[0]]
        for index in range(1, len(segments), 2):
            name = segments[index]
            value = values.get(name, _MISSING)
            if value is _MISSING:
                if strict:
                    msg = f"missing variable {name!r} for key {key!r}"
                    raise InterpolationError(key, name, msg)
                if on_missing is None:
                    _log.debug("locjson: missing variable %r for key %r", name, key)
                else:
                    on_missing(key, locale, name)
                parts.append("{" + name + "}")
            else:
                parts.append(str(value))
            parts.append(segments[index + 1])
        return "".join(parts)


def compile_template(text: str) -> Template:
    """Compile catalog text into a :class:`Template`.

    Placeholders must be plain ASCII identifiers such as ``{name}`` or
    ``{_count2}``. Doubled braces (``{{`` and ``}}``) produce literal braces.

    Notes:
        - ``{a:}`` is treated exactly like ``{a}``: :meth:`string.Formatter.parse`
          reports an empty format spec the same way as no spec, and an empty
          spec carries no risk.
        - Placeholder names are ASCII-only in 0.1.0, so Turkish names such as
          ``{İsim}`` are rejected. Python NFKC-normalizes keyword argument
          names, so some non-ASCII names could never be filled through
          ``**vars``. Allowing more names later is a non-breaking change.

    Args:
        text: The raw catalog string.

    Returns:
        The compiled template.

    Raises:
        TemplateError: With one message per kind of problem: unbalanced
            braces, a conversion (``{x!r}``), a format spec (``{x:>10}``), a
            positional or empty placeholder (``{0}``, ``{}``), or a name that
            is not a plain ASCII identifier (``{a.b}``, ``{a[0]}``,
            ``{ name }``, ``{İsim}``).
    """
    try:
        parsed = list(_FORMATTER.parse(text))
    except ValueError as exc:
        msg = f"invalid brace syntax ({exc}); {_LITERAL_HINT}"
        raise TemplateError(msg) from None
    segments: list[str] = []
    literal: list[str] = []
    fields: set[str] = set()
    for chunk, field, spec, conversion in parsed:
        literal.append(chunk)
        if field is None:
            continue
        if conversion is not None:
            msg = (
                f"conversion '!{conversion}' is not allowed in placeholder "
                f"{{{field}}}; {_LITERAL_HINT}"
            )
            raise TemplateError(msg)
        if spec:
            msg = (
                f"format spec ':{spec}' is not allowed in placeholder {{{field}}}; "
                f"{_LITERAL_HINT}"
            )
            raise TemplateError(msg)
        if _POSITIONAL.fullmatch(field):
            msg = (
                f"positional or empty placeholder {{{field}}} is not allowed; "
                f"use a name like {{name}}, or {_LITERAL_HINT}"
            )
            raise TemplateError(msg)
        if not _NAME.fullmatch(field):
            msg = (
                f"placeholder {{{field}}} must be a plain ASCII name like "
                f"{{name}}; {_LITERAL_HINT}"
            )
            raise TemplateError(msg)
        segments.append("".join(literal))
        literal.clear()
        segments.append(field)
        fields.add(field)
    segments.append("".join(literal))
    return Template(text, tuple(segments), frozenset(fields))
