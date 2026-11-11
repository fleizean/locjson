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
from typing import TYPE_CHECKING, Final, Literal

from locjson.errors import InvalidLocaleError

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence

__all__ = ["direction", "fallback_chain", "negotiate", "normalize", "parents"]

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


def _without_likely_script(tag: str) -> str | None:
    """Return a canonical tag without its script, when that script is implied.

    The script is implied when it is the language's likely script, or when
    the language has a single script, as in :func:`parents`: ``pt-Latn-PT``
    gives ``pt-PT``. Internal: the plural-rule lookup uses it, so a tag that
    spells out its script finds the rule of the script-less tag.

    Args:
        tag: A canonical locale tag.

    Returns:
        The tag without its script subtag, or ``None`` when the tag has no
        script or its script is not implied (``zh-Hant-TW``, ``sr-Latn``).
    """
    language, script, region, variants = _split(tag)
    if script is None:
        return None
    likely = _LIKELY_SCRIPT.get(language)
    if likely is not None and likely != script:
        return None
    return "-".join([language, *([region] if region else []), *variants])


def _writing_system(tag: str) -> tuple[str, str | None]:
    """Return the language and effective script of a canonical tag.

    The script is the explicit script subtag, else the script the region
    implies (``zh-TW`` gives ``Hant``), else the language's likely script
    (``sr`` gives ``Cyrl``). A language without a likely-script entry and no
    script subtag gives ``None``. Internal: :meth:`Localizer.direction` uses
    it to take ``$meta.direction`` only from catalogs written in the same
    language and script as the requested locale.

    Args:
        tag: A canonical locale tag.

    Returns:
        ``(language, script)``, for example ``("zh", "Hant")`` for
        ``"zh-Hant-TW"`` and ``("ar", None)`` for ``"ar-EG"``.
    """
    language, script, region, _ = _split(tag)
    if script is None and region is not None:
        script = _REGION_SCRIPT.get((language, region))
    if script is None:
        script = _LIKELY_SCRIPT.get(language)
    return language, script


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


MAX_HEADER_LENGTH: Final = 4096
"""Longest ``Accept-Language`` header :func:`negotiate` reads; longer ones are
ignored."""

MAX_HEADER_PIECES: Final = 64
"""How many comma-separated pieces of a header :func:`negotiate` examines."""

MAX_HEADER_ITEMS: Final = 32
"""How many valid language ranges of a header :func:`negotiate` keeps."""

# RFC 4647 section 2.1 basic language range ("*" is handled separately).
_RANGE: Final = re.compile(r"[A-Za-z]{1,8}(?:-[A-Za-z0-9]{1,8})*")
# RFC 9110 section 12.4.2 qvalue.
_QVALUE: Final = re.compile(r"0(?:\.[0-9]{0,3})?|1(?:\.0{0,3})?")
# RFC 9110 section 5.6.3 optional whitespace: spaces and horizontal tabs.
_OWS: Final = " \t"

# CLDR 49 cldr-core/scriptMetadata.json: every script with ``rtl: "YES"``.
RTL_SCRIPTS: Final = frozenset({
    "Adlm", "Arab", "Armi", "Avst", "Chrs", "Cprt", "Elym", "Gara", "Hatr",
    "Hebr", "Hung", "Khar", "Lydi", "Mand", "Mani", "Mend", "Merc", "Mero",
    "Narb", "Nbat", "Nkoo", "Orkh", "Ougr", "Palm", "Phli", "Phlp", "Phnx",
    "Prti", "Rohg", "Samr", "Sarb", "Sidt", "Sogd", "Sogo", "Syrc", "Thaa",
    "Yezi",
})  # fmt: skip
"""ISO 15924 codes of the scripts written right to left (CLDR 49)."""

# CLDR 49 cldr-core/supplemental/likelySubtags.json: base languages of the
# availableLocales.json "full" locales whose likely script is in RTL_SCRIPTS,
# plus dv (dv -> dv-Thaa-MV).
RTL_LANGUAGES: Final = frozenset({
    "ar", "bal", "ckb", "dv", "fa", "he", "ks", "lrc",
    "mzn", "nqo", "ps", "sd", "syr", "ug", "ur", "yi",
})  # fmt: skip
"""Languages written right to left in their likely script (CLDR 49)."""


def _quality(params: list[str]) -> float | None:
    """Return the q weight of a header item, or ``None`` if it is malformed."""
    quality = 1.0
    for param in params:
        name, sep, value = param.partition("=")
        if name.strip(_OWS).lower() != "q":
            continue  # unknown parameters are ignored
        value = value.strip(_OWS)
        if not sep or _QVALUE.fullmatch(value) is None:
            return None
        quality = float(value)
    return quality


def _parse_accept_language(header: str) -> tuple[list[str], set[str]]:
    """Return the acceptable tags by preference, and the excluded tags."""
    weighted: list[tuple[float, str]] = []
    excluded: set[str] = set()
    items = 0
    for piece in header.split(",", MAX_HEADER_PIECES)[:MAX_HEADER_PIECES]:
        language_range, *params = piece.strip(_OWS).split(";")
        language_range = language_range.strip(_OWS)
        if _RANGE.fullmatch(language_range) is None:
            continue  # empty piece, "*" or not a basic range
        quality = _quality(params)
        if quality is None:
            continue
        try:
            tag = normalize(language_range)
        except InvalidLocaleError:
            continue
        if quality == 0:
            excluded.add(tag)
        else:
            weighted.append((quality, tag))
        items += 1
        if items == MAX_HEADER_ITEMS:
            break
    weighted.sort(key=lambda item: -item[0])  # stable: ties keep header order
    return [tag for _, tag in weighted], excluded


def negotiate(
    accept_language: str | None, available: Iterable[str], default: str
) -> str:
    """Pick the best available locale for an ``Accept-Language`` header.

    The header is parsed per RFC 9110: items are ordered by their ``q``
    weight, ties keep header order, ``q=0`` marks a locale as not
    acceptable, and ``*`` or malformed items are ignored. Each item is then
    matched with RFC 4647 Lookup, walking the same script-aware
    :func:`parents` as the fallback chain, so ``zh-TW`` matches ``zh-Hant``
    and never ``zh``.

    The header is untrusted input and never causes an exception: a missing,
    empty, malformed or over-long header (see :data:`MAX_HEADER_LENGTH`,
    :data:`MAX_HEADER_PIECES` and :data:`MAX_HEADER_ITEMS`) gives
    ``default``.

    Args:
        accept_language: The raw header value, or ``None`` if absent.
        available: The locales the application can serve.
        default: The locale returned when nothing matches.

    Returns:
        The canonical form of the chosen locale.

    Raises:
        InvalidLocaleError: If an ``available`` locale or ``default`` is not
            a valid locale tag. These are configuration, not request input.
    """
    supported = frozenset(normalize(tag) for tag in available)
    fallback = normalize(default)
    header: object = accept_language
    if not isinstance(header, str) or len(header) > MAX_HEADER_LENGTH:
        return fallback
    candidates, excluded = _parse_accept_language(header)
    for tag in candidates:
        for candidate in (tag, *parents(tag)):
            if candidate in supported and candidate not in excluded:
                return candidate
    return fallback


def direction(locale: str) -> Literal["ltr", "rtl"]:
    """Return the text direction of a locale from the built-in CLDR tables.

    An explicit script decides (``pa-Arab`` is right to left, ``ks-Deva`` is
    left to right). A script-less tag uses the script its region implies,
    then the language's likely script. Catalog ``$meta.direction`` values are
    not consulted here.

    Args:
        locale: A locale tag such as ``"ar"`` or ``"pa-Arab"``.

    Returns:
        ``"rtl"`` or ``"ltr"``. An invalid tag gives ``"ltr"`` and never
        raises.
    """
    try:
        tag = normalize(locale)
    except InvalidLocaleError:
        return "ltr"
    language, script, region, _ = _split(tag)
    if script is None and region is not None:
        script = _REGION_SCRIPT.get((language, region))
    if script is not None:
        return "rtl" if script in RTL_SCRIPTS else "ltr"
    return "rtl" if language in RTL_LANGUAGES else "ltr"
