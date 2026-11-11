"""Strict UTF-8 JSON reading and RFC 6901 pointer helpers (internal).

JSON-level faults that have a location (duplicate keys, ``NaN`` and
``Infinity``) are not raised here. They are recorded as markers in the parsed
document, so :func:`locjson.catalog.build_catalog` can report each one with
its JSON pointer: :class:`JsonObject` remembers repeated keys and
:class:`NonFinite` stands in for a non-finite constant.
"""

from __future__ import annotations

import json

from locjson._compat import override
from locjson.errors import InvalidCatalogError

__all__ = ["JsonObject", "NonFinite", "escape_pointer_token", "read_json"]


class JsonObject(dict[str, object]):
    """A decoded JSON object that remembers its repeated keys.

    The value of a repeated key is the last one in the file, as with
    :func:`json.loads`; the repetition itself is kept so it can be reported.

    Attributes:
        duplicates: Each repeated key, once per extra occurrence, in file order.
    """

    __slots__ = ("duplicates",)

    duplicates: tuple[str, ...]


class NonFinite:
    """Marker for a ``NaN``, ``Infinity`` or ``-Infinity`` constant.

    These are not valid JSON (RFC 8259), but :mod:`json` accepts them. The
    marker keeps the value from being mistaken for a number.

    Attributes:
        name: The constant exactly as written in the file.
    """

    __slots__ = ("name",)

    name: str

    def __init__(self, name: str) -> None:
        self.name = name

    @override
    def __repr__(self) -> str:
        return f"NonFinite({self.name!r})"


def _pairs_hook(pairs: list[tuple[str, object]]) -> JsonObject:
    obj = JsonObject()
    duplicates: list[str] = []
    for key, value in pairs:
        if key in obj:
            duplicates.append(key)
        obj[key] = value
    obj.duplicates = tuple(duplicates)
    return obj


def read_json(raw: bytes, *, origin: str) -> object:
    """Decode and parse one catalog file.

    The bytes are decoded as strict UTF-8; a single leading BOM is accepted.
    Decoding never depends on the platform's locale encoding. Objects are
    returned as :class:`JsonObject` and non-finite constants as
    :class:`NonFinite`, so the catalog validator can report them with their
    JSON pointers.

    Args:
        raw: The file content.
        origin: The file's path relative to the catalog root, used in errors.

    Returns:
        The parsed JSON value.

    Raises:
        InvalidCatalogError: If the bytes are not UTF-8, not valid JSON, or
            nested too deeply for the parser. The error points at the whole
            document (pointer ``""``).
    """
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise InvalidCatalogError("file is not valid UTF-8", path=origin) from None
    try:
        data: object = json.loads(
            text, object_pairs_hook=_pairs_hook, parse_constant=NonFinite
        )
    except json.JSONDecodeError as exc:
        problem = f"line {exc.lineno}, column {exc.colno}: {exc.msg}"
        raise InvalidCatalogError(problem, path=origin) from None
    except RecursionError:
        raise InvalidCatalogError("JSON nesting is too deep", path=origin) from None
    return data


def escape_pointer_token(token: str) -> str:
    """Escape one reference token for an RFC 6901 JSON pointer.

    Args:
        token: A raw JSON object key.

    Returns:
        The token with ``~`` escaped as ``~0`` and then ``/`` as ``~1``.
    """
    return token.replace("~", "~0").replace("/", "~1")
