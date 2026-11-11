"""Locale tag normalization and script-aware fallback chains.

Tags are BCP 47 language tags (RFC 5646) in a restricted, canonical form:
``language[-Script][-REGION][-variant...]``. POSIX locale names such as
``tr_TR.UTF-8`` are accepted as input. Extensions and private-use subtags are
dropped, because catalogs are never keyed by them.

The tables in this module are small, hand-picked extracts of CLDR 49
(``cldr-json`` tag ``49.0.0``). Each table names its source file.
"""

from __future__ import annotations

import functools
import re
from typing import TYPE_CHECKING, Final

from locjson.errors import InvalidLocaleError

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

__all__ = ["fallback_chain", "normalize", "parents"]

MAX_TAG_LENGTH: Final = 128
"""Longest raw tag accepted by :func:`normalize`, POSIX suffixes included."""

_REPR_LIMIT: Final = 64

# RFC 5646 section 2.1 ``langtag``, restricted to a 2-3 letter language with at
# most one extlang. Irregular tags (``i-klingon``), private-use-only tags
# (``x-foo``) and 4-8 letter languages (``root``, ``common``) never match.
# Matched against the lowercased tag.
_LANGTAG: Final = re.compile(
    r"""
    (?P<language>[a-z]{2,3})
    (?:-(?P<extlang>[a-z]{3}))?
    (?:-(?P<script>[a-z]{4}))?
    (?:-(?P<region>[a-z]{2}|[0-9]{3}))?
    (?P<variants>(?:-(?:[a-z0-9]{5,8}|[0-9][a-z0-9]{3}))*)
    (?P<extensions>(?:-[a-wyz0-9](?:-[a-z0-9]{2,8})+)*)
    (?P<privateuse>-x(?:-[a-z0-9]{1,8})+)?
    """,
    re.VERBOSE,
)

# CLDR 49 cldr-core/supplemental/aliases.json, languageAlias entries with
# ``_reason: deprecated`` and a single-language replacement. Legacy and
# macrolanguage aliases (tl, sh, cmn, arb) are left out on purpose: applying
# them would silently rename existing catalog files.
_LANGUAGE_ALIASES: Final[Mapping[str, str]] = {
    "iw": "he",
    "in": "id",
    "ji": "yi",
    "jw": "jv",
    "mo": "ro",
}

# CLDR 49 cldr-core/supplemental/likelySubtags.json: the likely script of every
# language that has a script-subtagged locale in availableLocales.json, plus
# mn, ms and ha. A script other than this one is a "nonlikelyScript", whose
# parent is root (parentLocales.json ``_localeRules``), so it is never
# truncated to the bare language. Languages missing here have one script, and
# any script subtag on them may be dropped.
_LIKELY_SCRIPT: Final[Mapping[str, str]] = {
    "az": "Latn",
    "bal": "Arab",
    "bs": "Latn",
    "ff": "Latn",
    "ha": "Latn",
    "hi": "Deva",
    "kk": "Cyrl",
    "kok": "Deva",
    "ks": "Arab",
    "ku": "Latn",
    "kxv": "Latn",
    "mn": "Cyrl",
    "mni": "Beng",
    "ms": "Latn",
    "pa": "Guru",
    "sat": "Olck",
    "sd": "Arab",
    "shi": "Tfng",
    "sr": "Cyrl",
    "su": "Latn",
    "suz": "Deva",
    "uz": "Latn",
    "vai": "Vaii",
    "yue": "Hant",
    "zh": "Hans",
}

# CLDR 49 cldr-core/supplemental/likelySubtags.json: the script implied by a
# region for a script-less tag. Only these six rows ship in 0.1.0.
_REGION_SCRIPT: Final[Mapping[tuple[str, str], str]] = {
    ("zh", "TW"): "Hant",
    ("zh", "HK"): "Hant",
    ("zh", "MO"): "Hant",
    ("zh", "CN"): "Hans",
    ("zh", "SG"): "Hans",
    ("zh", "MY"): "Hans",
}


def _invalid(tag: object, reason: str = "") -> InvalidLocaleError:
    shown = repr(tag)
    if len(shown) > _REPR_LIMIT:
        shown = shown[: _REPR_LIMIT - 3] + "..."
    detail = f" ({reason})" if reason else ""
    return InvalidLocaleError(tag, f"invalid locale tag: {shown}{detail}")


def normalize(tag: str) -> str:
    """Return the canonical BCP 47 form of a locale tag.

    The steps, in order:

    1. Reject non-strings and tags longer than :data:`MAX_TAG_LENGTH`.
    2. Reject non-ASCII text before any case mapping, so the Turkish dotted
       and dotless i (U+0130, U+0131) can never be case-folded into a valid
       tag.
    3. Strip a POSIX ``@modifier`` and then a ``.codeset``
       (``tr_TR.UTF-8@euro`` becomes ``tr_TR``). The ``@latin`` and
       ``@cyrillic`` modifiers are stripped as well, not mapped to a script.
    4. Reject the POSIX ``C`` and ``POSIX`` locales.
    5. Accept ``_`` as a separator.
    6. Match the RFC 5646 grammar (2-3 letter language, optional extlang,
       script, region, variants, extensions and private use).
    7. Drop extensions and private use.
    8. Replace a language that has an extlang with the extlang
       (``zh-yue-HK`` becomes ``yue-HK``).
    9. Apply the deprecated-language aliases ``iw``, ``in``, ``ji``, ``jw``
       and ``mo``.
    10. Reject ``und``.
    11. Reject repeated variants.
    12. Recase: language and variants lowercase, script titlecase, region
        uppercase.

    Results are cached in a bounded LRU cache of 1024 entries.

    Args:
        tag: A locale tag such as ``"en"``, ``"pt_BR"`` or ``"zh-hant-tw"``.

    Returns:
        The canonical tag, for example ``"zh-Hant-TW"``.

    Raises:
        InvalidLocaleError: If ``tag`` is not a string or is not a valid tag
            after the steps above.
    """
    value: object = tag
    if not isinstance(value, str):
        raise _invalid(value, "not a string")
    if len(value) > MAX_TAG_LENGTH:
        raise _invalid(value, f"longer than {MAX_TAG_LENGTH} characters")
    return _normalize(value)


@functools.lru_cache(maxsize=1024)
def _normalize(tag: str) -> str:
    # Checked before any case mapping: "İ".lower() is two code points.
    if not tag.isascii():
        raise _invalid(tag, "not ASCII")
    posix = tag.partition("@")[0].partition(".")[0]
    if posix.lower() in {"c", "posix"}:
        raise _invalid(tag, "POSIX C locale")
    match = _LANGTAG.fullmatch(posix.replace("_", "-").lower())
    if match is None:
        raise _invalid(tag)
    language = match["extlang"] or match["language"]
    language = _LANGUAGE_ALIASES.get(language, language)
    if language == "und":
        raise _invalid(tag, "undetermined language")
    variants = match["variants"].split("-")[1:]
    if len(set(variants)) != len(variants):
        raise _invalid(tag, "repeated variant")
    parts = [language]
    if script := match["script"]:
        parts.append(script[0].upper() + script[1:])
    if region := match["region"]:
        parts.append(region.upper())
    parts.extend(variants)
    return "-".join(parts)


_SCRIPT_LENGTH: Final = 4
_REGION_LENGTHS: Final = frozenset({2, 3})


def _split(tag: str) -> tuple[str, str | None, str | None, list[str]]:
    """Split a canonical tag into language, script, region and variants."""
    language, *rest = tag.split("-")
    script = region = None
    # Variants are at least four characters and a four-character variant
    # starts with a digit, so neither test below can match a variant.
    if rest and len(rest[0]) == _SCRIPT_LENGTH and rest[0].isalpha():
        script = rest.pop(0)
    if rest and len(rest[0]) in _REGION_LENGTHS:
        region = rest.pop(0)
    return language, script, region, rest


def parents(tag: str) -> tuple[str, ...]:
    """Return the script-aware truncations of a locale tag, most specific first.

    Variants are dropped first, then the region. A tag with a region but no
    script gets the script its region implies (``zh-TW`` gives ``zh-Hant``).
    The script is dropped only when it is the language's likely script, so
    ``zh-Hant`` and ``sr-Latn`` never fall back to ``zh`` or ``sr``, which are
    written in a different script. A script on a language with a single
    script may always be dropped (``de-Latn`` gives ``de``).

    Args:
        tag: A locale tag. It is normalized first.

    Returns:
        The parents of ``tag``, excluding ``tag`` itself. For example
        ``("zh-Hant",)`` for ``"zh-Hant-TW"`` and ``("zh-Hans", "zh")`` for
        ``"zh-CN"``.

    Raises:
        InvalidLocaleError: If ``tag`` is not a valid locale tag.
    """
    language, script, region, variants = _split(normalize(tag))
    base = [subtag for subtag in (language, script, region) if subtag]
    out = ["-".join(base + variants[:end]) for end in range(len(variants) - 1, -1, -1)]
    if region is not None:
        implied = script or _REGION_SCRIPT.get((language, region))
        if implied is not None:
            out.append(f"{language}-{implied}")
            script = implied
    if script is not None:
        likely = _LIKELY_SCRIPT.get(language)
        if likely is not None and likely != script:
            # CLDR nonlikelyScript -> root: never serve another script.
            return tuple(out)
    if region is not None or script is not None:
        out.append(language)
    return tuple(out)


def fallback_chain(
    tag: str, fallbacks: Mapping[str, Sequence[str]], default: str
) -> tuple[str, ...]:
    """Return the locales to try, in order, for a lookup in ``tag``.

    The chain starts with ``tag`` and its :func:`parents`. Every tag in the
    chain is followed immediately by its explicit ``fallbacks``, and each of
    those is expanded the same way (its parents, then its own fallbacks).
    ``default`` comes last. A tag appears only once, at its first position, so
    cyclic fallbacks terminate.

    For example, with ``fallbacks={"pt": ["es"]}`` the chain for ``"pt-BR"`` is
    ``("pt-BR", "pt", "es", default)``.

    Args:
        tag: The canonical requested locale.
        fallbacks: Explicit fallbacks per locale. Keys and values must be
            canonical tags.
        default: The canonical default locale, always tried last.

    Returns:
        The ordered, duplicate-free chain, ending with ``default``.

    Raises:
        InvalidLocaleError: If a tag in the chain is not a valid locale tag.
    """
    chain: list[str] = []
    seen: set[str] = set()

    def visit(start: str) -> None:
        for candidate in (start, *parents(start)):
            if candidate in seen:
                continue
            seen.add(candidate)
            chain.append(candidate)
            for extra in fallbacks.get(candidate, ()):
                visit(extra)

    visit(tag)
    if default not in seen:
        chain.append(default)
    return tuple(chain)
