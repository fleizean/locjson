"""Locale normalization, script-aware parents and fallback chains (LOC-01..03)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from locjson import DictLoader, InvalidLocaleError, Localizer, locale
from locjson.locale import MAX_TAG_LENGTH, fallback_chain, normalize, parents

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from tests.conftest import Catalogs, MakeLocalesDir


# --- normalize ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "canonical"),
    [
        ("pt_BR", "pt-BR"),
        ("en_us", "en-US"),
        ("tr_TR.UTF-8", "tr-TR"),
        ("tr_TR.UTF-8@euro", "tr-TR"),
        ("zh-hant-tw", "zh-Hant-TW"),
        ("ZH_hANT_tw", "zh-Hant-TW"),
        ("iw", "he"),
        ("in-ID", "id-ID"),
        ("ji", "yi"),
        ("jw", "jv"),
        ("mo", "ro"),
        ("en-US-u-ca-gregory-x-foo", "en-US"),
        ("zh-yue-HK", "yue-HK"),
        ("sr_RS@latin", "sr-RS"),
        ("sr_RS@cyrillic", "sr-RS"),
        ("de-CH-1996", "de-CH-1996"),
        ("es-419", "es-419"),
        ("ca-es-VALENCIA", "ca-ES-valencia"),
        ("no", "no"),
        ("tl", "tl"),
        ("sh", "sh"),
    ],
)
def test_normalize(raw: str, canonical: str) -> None:
    assert normalize(raw) == canonical
    assert normalize(canonical) == canonical


@pytest.mark.parametrize(
    "raw",
    [
        "x-private",
        "i-klingon",
        "und",
        "und-Latn",
        "C",
        "POSIX",
        "posix",
        "C.UTF-8",
        "",
        "İt",
        "tr-İ",
        "en--US",
        "en-",
        "root",
        "common",
        "../../etc",
        "en-US-US",
        "de-1996-1996",
        "a" * 129,
        42,
        None,
    ],
)
def test_normalize_rejects(raw: Any) -> None:
    with pytest.raises(InvalidLocaleError) as info:
        normalize(raw)
    assert info.value.tag == raw


def test_normalize_never_uses_turkish_case_mapping() -> None:
    assert normalize("TR") == "tr"
    assert normalize("tr-tr") == "tr-TR"
    assert normalize("TR_TR") == "tr-TR"
    for raw in ("İt", "tr-İ", "tr-TR-ı", "TRİ"):
        with pytest.raises(InvalidLocaleError, match="not ASCII"):
            normalize(raw)


def test_length_cap_counts_dropped_subtags() -> None:
    exact = "en-US-u-" + "-".join(["abcdefgh"] * 13)
    exact += "-" + "a" * (MAX_TAG_LENGTH - len(exact) - 1)
    assert len(exact) == MAX_TAG_LENGTH
    assert normalize(exact) == "en-US"
    with pytest.raises(InvalidLocaleError, match="longer than 128"):
        normalize(exact + "b")


def test_error_message_truncates_the_tag() -> None:
    with pytest.raises(InvalidLocaleError) as info:
        normalize("q" * 500)
    message = str(info.value)
    assert len(message) < 120
    assert "..." in message
    assert info.value.tag == "q" * 500


def test_normalize_cache_is_bounded_lru() -> None:
    assert locale._normalize.cache_parameters()["maxsize"] == 1024
    normalize("pt_BR")
    before = locale._normalize.cache_info().hits
    normalize("pt_BR")
    assert locale._normalize.cache_info().hits == before + 1


def test_region_script_table_has_the_six_locked_rows() -> None:
    assert len(locale._REGION_SCRIPT) == 6
    assert locale._LANGUAGE_ALIASES == {
        "iw": "he",
        "in": "id",
        "ji": "yi",
        "jw": "jv",
        "mo": "ro",
    }
    assert len(locale._LIKELY_SCRIPT) == 25


# --- parents and fallback_chain -----------------------------------------------


@pytest.mark.parametrize(
    ("tag", "expected"),
    [
        ("en", ()),
        ("zh-Hant-TW", ("zh-Hant",)),
        ("zh-TW", ("zh-Hant",)),
        ("zh-Hans", ("zh",)),
        ("zh-Hant", ()),
        ("ca-ES-valencia", ("ca-ES", "ca")),
        ("de-CH-1996-fonipa", ("de-CH-1996", "de-CH", "de")),
        ("pa-Arab-PK", ("pa-Arab",)),
        ("zh_tw", ("zh-Hant",)),
    ],
)
def test_parents(tag: str, expected: tuple[str, ...]) -> None:
    assert parents(tag) == expected


@pytest.mark.parametrize(
    ("tag", "chain"),
    [
        ("zh-Hant-TW", "zh-Hant-TW zh-Hant en"),
        ("zh-Hans-CN", "zh-Hans-CN zh-Hans zh en"),
        ("sr-Latn-RS", "sr-Latn-RS sr-Latn en"),
        ("zh-TW", "zh-TW zh-Hant en"),
        ("zh-HK", "zh-HK zh-Hant en"),
        ("zh-MO", "zh-MO zh-Hant en"),
        ("zh-CN", "zh-CN zh-Hans zh en"),
        ("zh-SG", "zh-SG zh-Hans zh en"),
        ("zh-MY", "zh-MY zh-Hans zh en"),
        ("zh-US", "zh-US zh en"),
        ("tr-CY", "tr-CY tr en"),
        ("ca-ES-valencia", "ca-ES-valencia ca-ES ca en"),
        ("de-Latn-DE", "de-Latn-DE de-Latn de en"),
        ("uz-Cyrl", "uz-Cyrl en"),
        ("en-GB", "en-GB en"),
        ("en", "en"),
    ],
)
def test_fallback_chain(tag: str, chain: str) -> None:
    assert fallback_chain(tag, {}, "en") == tuple(chain.split())


@pytest.mark.parametrize(
    ("tag", "fallbacks", "chain"),
    [
        ("pt-BR", {"pt-BR": ["pt"]}, "pt-BR pt en"),
        ("pt-BR", {"pt": ["es"]}, "pt-BR pt es en"),
        ("gsw", {"gsw": ["de-CH"]}, "gsw de-CH de en"),
        ("aa", {"aa": ["bb"], "bb": ["aa"]}, "aa bb en"),
        # A fallback is followed by its own fallbacks before its parents.
        ("pt-BR", {"pt-BR": ["pt-PT"], "pt-PT": ["es"]}, "pt-BR pt-PT es pt en"),
        ("de-AT", {"de": ["en"]}, "de-AT de en"),
    ],
)
def test_explicit_fallbacks_apply_to_every_chain_tag(
    tag: str, fallbacks: Mapping[str, Sequence[str]], chain: str
) -> None:
    assert fallback_chain(tag, fallbacks, "en") == tuple(chain.split())


def test_fallback_chain_never_serves_another_script() -> None:
    for tag in ("zh-TW", "zh-Hant", "zh-Hant-TW", "zh-HK"):
        assert "zh" not in fallback_chain(tag, {}, "en")
    assert "sr" not in fallback_chain("sr-Latn-RS", {}, "en")


# --- end to end through Localizer -----------------------------------------------


def test_localizer_follows_the_script_aware_chain(
    make_locales_dir: MakeLocalesDir, sample_catalogs: Catalogs
) -> None:
    for l10n in (
        Localizer(make_locales_dir(), fallbacks={"pt-BR": ["pt"]}),
        Localizer(loader=DictLoader(sample_catalogs), fallbacks={"pt-BR": ["pt"]}),
    ):
        assert l10n.t("nav.home", locale="pt_BR") == "Início"
        assert l10n.t("nav.settings", locale="pt_BR") == "Configurações"
        assert l10n.t("nav.home", locale="zh-TW") == "首頁"
        assert l10n.t("nav.home", locale="zh_hant_tw") == "首頁"
        assert l10n.t("nav.settings", locale="zh-TW") == "Settings"
        assert l10n.t("nav.settings", locale="zh-Hant") == "Settings"
        assert l10n.t("nav.settings", locale="zh-CN") == "设置"
        assert l10n.t("nav.home", locale="tr_TR.UTF-8") == "Ana Sayfa"


def test_localizer_truncates_region_without_explicit_fallbacks(
    make_locales_dir: MakeLocalesDir,
) -> None:
    l10n = Localizer(make_locales_dir())
    assert l10n.t("nav.home", locale="pt-BR") == "Início"
    assert l10n.t("nav.home", locale="tr-CY") == "Ana Sayfa"
