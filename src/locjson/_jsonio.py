"""Strict UTF-8 JSON reading and RFC 6901 pointer helpers (internal)."""

from __future__ import annotations

import json

from locjson.errors import InvalidCatalogError

__all__ = ["escape_pointer_token", "read_json"]


def read_json(raw: bytes, *, origin: str) -> object:
    """Decode and parse one catalog file.

    The bytes are decoded as strict UTF-8; a single leading BOM is accepted.
    Decoding never depends on the platform's locale encoding.

    Args:
        raw: The file content.
        origin: The file's path relative to the catalog root, used in errors.

    Returns:
        The parsed JSON value.

    Raises:
        InvalidCatalogError: If the bytes are not UTF-8 or not valid JSON. The
            error points at the whole document (pointer ``""``).
    """
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise InvalidCatalogError("file is not valid UTF-8", path=origin) from None
    try:
        data: object = json.loads(text)
    except json.JSONDecodeError as exc:
        problem = f"line {exc.lineno}, column {exc.colno}: {exc.msg}"
        raise InvalidCatalogError(problem, path=origin) from None
    return data


def escape_pointer_token(token: str) -> str:
    """Escape one reference token for an RFC 6901 JSON pointer.

    Args:
        token: A raw JSON object key.

    Returns:
        The token with ``~`` escaped as ``~0`` and then ``/`` as ``~1``.
    """
    return token.replace("~", "~0").replace("/", "~1")
