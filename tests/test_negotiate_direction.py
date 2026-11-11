"""Accept-Language negotiation (LOC-04) and text direction (LOC-05)."""

from __future__ import annotations

from typing import Any, Literal

import pytest

from locjson import DictLoader, InvalidLocaleError, Localizer, locale
from locjson.locale import (
    MAX_HEADER_ITEMS,
    MAX_HEADER_LENGTH,
    MAX_HEADER_PIECES,
    direction,
    negotiate,
)

AVAILABLE = frozenset({"en", "tr", "pt", "zh-Hant", "de"})


# --- negotiate ------------------------------------------------------------------


def test_negotiate_picks_highest_quality_match() -> None:
    assert negotiate("tr-TR,tr;q=0.9,en;q=0.8", AVAILABLE, "en") == "tr"


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        ("tr-TR,tr;q=0.9,en;q=0.8", "tr"),
        ("fr-CH, fr;q=0.9, en;q=0.8, de;q=0.7, *;q=0.5", "en"),
        ("zh-TW", "zh-Hant"),
        ("zh-Hant-HK", "zh-Hant"),
        ("pt-BR", "pt"),
        ("de;q=0.5, tr;q=0.5", "de"),
        ("de;q=1.5, tr", "tr"),
        ("  , ,tr ;Q=0.3", "tr"),
        ("\ttr\t;\tq=0.3", "tr"),
        ("garbage!!", "en"),
        ("", "en"),
        ("*", "en"),
        ("en;q=0, tr;q=0", "en"),
        ("de;q=0.1, tr;q=0.9", "tr"),
        ("de;q=1.000, tr;q=0.999", "de"),
        ("de;q=1., tr;q=0.", "de"),
        ("de;q=.5, tr;q=0.1", "tr"),
        ("de;q=0.5000, tr;q=0.1", "tr"),
        ("de;q=1.001, tr;q=0.1", "tr"),
        ("de;q=, tr;q=0.1", "tr"),
        ("de;q, tr;q=0.1", "tr"),
        ("de;level=1;q=0.2, tr;q=0.1", "de"),
        ("de;, tr;q=0.1", "de"),
        ("pt_BR", "en"),
        ("x-klingon, i-klingon, und, tr;q=0.1", "tr"),
        ("tr-TR;q=0.9, tr;q=0", "en"),
        ("zh-CN, zh-TW;q=0.5", "zh-Hant"),
        ("DE", "de"),
        ("de-CH-1996", "de"),
        ("en-US-u-ca-gregory", "en"),
        ("123", "en"),
        ("toolongsubtag", "en"),
    ],
)
def test_negotiate_table(header: str, expected: str) -> None:
    assert negotiate(header, AVAILABLE, "en") == expected


def test_negotiate_none_returns_default() -> None:
    assert negotiate(None, AVAILABLE, "tr") == "tr"


def test_negotiate_non_string_header_returns_default() -> None:
    header: Any = b"tr"
    assert negotiate(header, AVAILABLE, "en") == "en"


def test_negotiate_over_long_header_returns_default() -> None:
    header = "tr," + "x" * (MAX_HEADER_LENGTH - 3)
    assert len(header) == MAX_HEADER_LENGTH
    assert negotiate(header, AVAILABLE, "en") == "tr"
    assert negotiate(header + "x", AVAILABLE, "en") == "en"


def _two_letter_tags(count: int) -> list[str]:
    letters = "abcfghijklmnopqrsuvwxyz"  # avoids d, e and t
    return [a + b for a in letters for b in letters][:count]


def test_negotiate_keeps_at_most_32_items() -> None:
    assert MAX_HEADER_ITEMS == 32
    filler = _two_letter_tags(MAX_HEADER_ITEMS)
    header = ", ".join([*filler, "tr", *_two_letter_tags(40)[32:]])
    assert negotiate(header, AVAILABLE, "en") == "en"
    within = ", ".join([*filler[:-1], "tr"])
    assert negotiate(within, AVAILABLE, "en") == "tr"


def test_negotiate_examines_at_most_64_pieces() -> None:
    assert MAX_HEADER_PIECES == 64
    junk = ["!"] * (MAX_HEADER_PIECES - 1)
    assert negotiate(", ".join([*junk, "tr"]), AVAILABLE, "en") == "tr"
    assert negotiate(", ".join([*junk, "!", "tr"]), AVAILABLE, "en") == "en"


def test_negotiate_normalizes_available_and_default() -> None:
    assert negotiate("pt-BR", ["pt_BR", "en_US"], "en_us") == "pt-BR"
    assert negotiate("fr", ["pt_BR", "en_US"], "en_us") == "en-US"
    assert negotiate("zh-TW", ("zh-hant", "en"), "en") == "zh-Hant"


@pytest.mark.parametrize(
    ("available", "default"),
    [(["en", "english"], "en"), (["en"], "und"), (["en", ""], "en"), (["en"], "C")],
)
def test_negotiate_rejects_invalid_configuration(
    available: list[str], default: str
) -> None:
    with pytest.raises(InvalidLocaleError):
        negotiate("tr", available, default)


@pytest.mark.parametrize(
    "header",
    ["\x00", ";;;", "q=1", "tr;q=0.5;q=x", "İt", "tr-İ", "-", "--", "a-", ",,,"],
)
def test_negotiate_never_raises_on_header(header: str) -> None:
    assert negotiate(header, AVAILABLE, "en") in {"en", "tr"}


# --- direction ------------------------------------------------------------------


def test_direction_of_arabic_is_rtl() -> None:
    assert direction("ar") == "rtl"


@pytest.mark.parametrize(
    "tag",
    [
        "ar",
        "ar-EG",
        "he",
        "fa",
        "ur",
        "yi",
        "dv",
        "ckb",
        "ps",
        "sd",
        "ug",
        "iw",
        "ji",
        "pa-Arab",
        "az-Arab",
        "ms-Arab",
        "uz-Arab-AF",
        "syr",
        "nqo",
    ],
)
def test_direction_rtl(tag: str) -> None:
    assert direction(tag) == "rtl"


@pytest.mark.parametrize(
    "tag",
    [
        "en",
        "tr",
        "zh-Hant",
        "zh-TW",
        "ja",
        "ks-Deva",
        "sd-Deva",
        "pa",
        "az",
        "ar-Latn",
        "../../etc",
        "",
        "und",
        "C",
        "İt",
    ],
)
def test_direction_ltr(tag: str) -> None:
    assert direction(tag) == "ltr"


def test_direction_never_raises_on_non_strings() -> None:
    value: Any = None
    assert direction(value) == "ltr"


def test_rtl_tables_are_the_cldr_49_extracts() -> None:
    assert len(locale.RTL_SCRIPTS) == 37
    assert {"Arab", "Hebr", "Thaa", "Syrc", "Nkoo", "Adlm", "Rohg"} <= (
        locale.RTL_SCRIPTS
    )
    rtl_languages = {"ar", "bal", "ckb", "dv", "fa", "he", "ks", "lrc"}
    rtl_languages |= {"mzn", "nqo", "ps", "sd", "syr", "ug", "ur", "yi"}
    assert rtl_languages == locale.RTL_LANGUAGES


# --- Localizer.direction: $meta only from same-language, same-script catalogs ---


def _localizer(
    catalogs: dict[str, dict[str, Any]],
    *,
    default_locale: str = "en",
    fallbacks: dict[str, list[str]] | None = None,
) -> Localizer:
    return Localizer(
        loader=DictLoader(catalogs),
        default_locale=default_locale,
        fallbacks=fallbacks,
    )


def test_rtl_locales_never_inherit_the_default_locales_ltr_meta() -> None:
    l10n = _localizer(
        {"en": {"$meta": {"direction": "ltr"}, "a": "A"}, "ar": {"a": "x"}}
    )
    assert (l10n.direction("ar"), l10n.direction("he")) == ("rtl", "rtl")
    assert l10n.direction("en") == "ltr"


def test_an_ltr_locale_never_inherits_the_default_locales_rtl_meta() -> None:
    l10n = _localizer(
        {"ar": {"$meta": {"direction": "rtl"}, "a": "x"}, "tr": {"a": "y"}},
        default_locale="ar",
    )
    assert l10n.direction("tr") == "ltr"
    assert l10n.direction("de") == "ltr"


def test_explicit_fallbacks_to_another_language_are_ignored() -> None:
    l10n = _localizer(
        {"en": {"a": "A"}, "fa": {"$meta": {"direction": "ltr"}, "a": "x"}},
        fallbacks={"ur": ["fa"], "tr": ["fa"]},
    )
    assert l10n.direction("ur") == "rtl"
    assert l10n.direction("tr") == "ltr"


@pytest.mark.parametrize("declared", ["ltr", "rtl"])
def test_a_regional_locale_inherits_its_language_meta(
    declared: Literal["ltr", "rtl"],
) -> None:
    l10n = _localizer({"en": {"a": "A"}, "ar": {"$meta": {"direction": declared}}})
    assert l10n.direction("ar-EG") == declared


def test_a_locale_without_any_matching_meta_uses_the_table() -> None:
    l10n = _localizer({"en": {"$meta": {"direction": "ltr"}, "a": "A"}})
    assert l10n.direction("he") == "rtl"
    assert l10n.direction("he-IL") == "rtl"
    assert l10n.direction("pa-Arab") == "rtl"


def test_a_script_locale_uses_the_meta_of_the_same_script() -> None:
    l10n = _localizer(
        {
            "en": {"a": "A"},
            "zh": {"$meta": {"direction": "rtl"}},
            "zh-Hant": {"$meta": {"direction": "ltr"}},
        }
    )
    assert l10n.direction("zh-Hant-TW") == "ltr"
    assert l10n.direction("zh-TW") == "ltr"
    # zh-CN -> zh-Hans -> zh: Hans is zh's likely script, so zh's $meta counts.
    assert l10n.direction("zh-CN") == "rtl"
    assert l10n.direction("zh-Hans") == "rtl"


def test_another_script_of_the_same_language_is_ignored() -> None:
    meta: dict[str, Any] = {"$meta": {"direction": "rtl"}, "a": "x"}
    l10n = _localizer({"sr": meta}, default_locale="sr")
    assert l10n.direction("sr-Latn") == "ltr"
    assert l10n.direction("sr-Cyrl") == "rtl"
    assert l10n.direction("sr-RS") == "rtl"
    by_fallback = _localizer(
        {"en": {"a": "A"}, "sr": meta}, fallbacks={"sr-Latn": ["sr"]}
    )
    assert by_fallback.direction("sr-Latn") == "ltr"


def test_the_locales_own_meta_wins_over_its_parents() -> None:
    l10n = _localizer(
        {
            "en": {"$meta": {"direction": "ltr"}, "a": "A"},
            "ar": {"$meta": {"direction": "rtl"}},
            "ar-EG": {"$meta": {"direction": "ltr"}},
        }
    )
    assert l10n.direction("ar-EG") == "ltr"
    assert l10n.direction("ar-SA") == "rtl"


def test_the_first_matching_meta_along_the_chain_wins() -> None:
    l10n = _localizer(
        {
            "en": {"a": "A"},
            "ar-EG": {"a": "x"},
            "ar": {"$meta": {"direction": "ltr"}},
        }
    )
    assert l10n.direction("ar-EG") == "ltr"


def test_mismatched_catalogs_are_not_loaded() -> None:
    l10n = _localizer({"en": {"$meta": {"direction": "ltr"}, "a": "A"}})
    assert l10n.direction("ar") == "rtl"
    assert "en" not in l10n._snapshot.catalogs


def test_an_explicit_script_never_uses_the_meta_of_a_script_less_catalog() -> None:
    l10n = _localizer({"en": {"a": "A"}, "ar": {"$meta": {"direction": "rtl"}}})
    assert l10n.direction("ar-Latn") == "ltr"


@pytest.mark.parametrize(
    ("tag", "expected"),
    [
        ("ar", ("ar", None)),
        ("ar-EG", ("ar", None)),
        ("ar-Latn", ("ar", "Latn")),
        ("sr", ("sr", "Cyrl")),
        ("sr-Latn-RS", ("sr", "Latn")),
        ("zh-TW", ("zh", "Hant")),
        ("zh-Hant-TW", ("zh", "Hant")),
        ("zh", ("zh", "Hans")),
    ],
)
def test_writing_system(tag: str, expected: tuple[str, str | None]) -> None:
    assert locale._writing_system(tag) == expected
