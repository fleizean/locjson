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

from locjson._compat import override

if TYPE_CHECKING:
    from collections.abc import Mapping

__all__ = ["Template", "TemplateError", "compile_template"]

_FORMATTER = string.Formatter()
_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
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

    def render(self, values: Mapping[str, object]) -> str:
        """Fill the placeholders from ``values``.

        Each present value is inserted as ``str(value)`` and is never parsed
        again, so a value containing braces stays literal. A placeholder with no
        value is kept as the literal text ``{name}``.

        Args:
            values: Placeholder values by name.

        Returns:
            The rendered text.
        """
        segments = self._segments
        if len(segments) == 1:
            return segments[0]
        parts = [segments[0]]
        for index in range(1, len(segments), 2):
            name = segments[index]
            value = values.get(name, _MISSING)
            parts.append("{" + name + "}" if value is _MISSING else str(value))
            parts.append(segments[index + 1])
        return "".join(parts)


def compile_template(text: str) -> Template:
    """Compile catalog text into a :class:`Template`.

    Placeholders must be plain ASCII identifiers such as ``{name}``. Doubled
    braces (``{{`` and ``}}``) produce literal braces.

    Args:
        text: The raw catalog string.

    Returns:
        The compiled template.

    Raises:
        TemplateError: For unbalanced braces, conversions (``{x!r}``), format
            specs (``{x:>10}``), and placeholder names that are not plain ASCII
            identifiers (``{0}``, ``{a.b}``, ``{a[0]}``, ``{}``).
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
        if not _NAME.fullmatch(field):
            msg = (
                f"placeholder {{{field}}} must be a plain name like {{name}}; "
                f"{_LITERAL_HINT}"
            )
            raise TemplateError(msg)
        segments.append("".join(literal))
        literal.clear()
        segments.append(field)
        fields.add(field)
    segments.append("".join(literal))
    return Template(text, tuple(segments), frozenset(fields))
