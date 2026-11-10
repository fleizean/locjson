"""Locale tag normalization and fallback chains.

This module holds the minimal rules the runtime needs today: canonical casing
for ``language[-Script][-REGION]`` tags and a flat fallback chain. Script-aware
parents, aliases and POSIX forms extend these functions without changing their
signatures.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from locjson.errors import InvalidLocaleError

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

__all__ = ["fallback_chain", "normalize"]

_MAX_TAG_LENGTH = 128
_TAG = re.compile(r"([a-z]{2,3})(?:-([a-z]{4}))?(?:-([a-z]{2}|[0-9]{3}))?")


def normalize(tag: str) -> str:
    """Return the canonical form of a locale tag.

    The language is lowercased, the script titlecased and the region
    uppercased, using ASCII-only case mapping. ``_`` is accepted as a
    separator, so ``"pt_BR"`` becomes ``"pt-BR"``.

    Args:
        tag: A locale tag such as ``"en"``, ``"pt_BR"`` or ``"zh-hant-tw"``.

    Returns:
        The canonical tag, for example ``"zh-Hant-TW"``.

    Raises:
        InvalidLocaleError: If ``tag`` is not a string, is longer than 128
            characters, contains non-ASCII characters, or is not a
            ``language[-Script][-REGION]`` tag.
    """
    value: object = tag
    if not isinstance(value, str) or len(value) > _MAX_TAG_LENGTH:
        raise InvalidLocaleError(value)
    # Checked before any case mapping: "İ".lower() is two code points.
    if not value.isascii():
        raise InvalidLocaleError(value)
    match = _TAG.fullmatch(value.replace("_", "-").lower())
    if match is None:
        raise InvalidLocaleError(value)
    language, script, region = match.groups()
    parts = [language]
    if script:
        parts.append(script[0].upper() + script[1:])
    if region:
        parts.append(region.upper())
    return "-".join(parts)


def fallback_chain(
    tag: str, fallbacks: Mapping[str, Sequence[str]], default: str
) -> tuple[str, ...]:
    """Return the locales to try, in order, for a lookup in ``tag``.

    Args:
        tag: The canonical requested locale.
        fallbacks: Canonical explicit fallbacks per canonical locale.
        default: The canonical default locale, always tried last.

    Returns:
        ``tag``, then ``fallbacks[tag]``, then ``default``, without duplicates
        and in that order.
    """
    return tuple(dict.fromkeys((tag, *fallbacks.get(tag, ()), default)))
