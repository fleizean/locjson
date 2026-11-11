"""Localizer configuration, request-time tag safety, ``has``/``locales`` and caches."""

from __future__ import annotations

import itertools
import logging
import string
import threading
from typing import TYPE_CHECKING, Any

import pytest

from locjson import (
    ConfigurationError,
    DictLoader,
    InvalidCatalogError,
    InvalidLocaleError,
    Localizer,
    LocJsonError,
)
from locjson import locale as locale_module
from locjson import localizer as localizer_module

if TYPE_CHECKING:
    from tests.conftest import Catalogs, IoAudit, MakeLocalesDir


def _tag(length: int) -> str:
    """A valid tag of exactly ``length`` characters that normalizes to en-US."""
    tag = "en-US-u-" + "-".join(["abcdefgh"] * 13)
    return tag + "-" + "a" * (length - len(tag) - 1)


# --- constructor validation ----------------------------------------------------


@pytest.mark.parametrize(
    "options",
    [
        {"default_locale": "xx-!!"},
        {"fallbacks": {"pt-BR": ["not a tag"]}},
        {"fallbacks": {"bad tag": ["en"]}},
    ],
    ids=["default", "fallback-value", "fallback-key"],
)
def test_invalid_tags_raise_at_construction(
    sample_catalogs: Catalogs, options: dict[str, Any]
) -> None:
    with pytest.raises(InvalidLocaleError):
        Localizer(loader=DictLoader(sample_catalogs), **options)


@pytest.mark.parametrize(
    ("options", "match"),
    [
        ({"default_locale": "de"}, "not among the discovered locales"),
        ({"missing": "ignore"}, "missing="),
        ({"fallbacks": {"pt-BR": "pt"}}, "fallbacks"),
        ({"fallbacks": {"pt-BR": ["pt", 3]}}, "fallbacks"),
        ({"fallbacks": [("pt-BR", ["pt"])]}, "fallbacks"),
    ],
    ids=["default-not-found", "policy", "bare-string", "non-string", "not-mapping"],
)
def test_misconfiguration_raises_configuration_error(
    sample_catalogs: Catalogs, options: dict[str, Any], match: str
) -> None:
    with pytest.raises(ConfigurationError, match=match):
        Localizer(loader=DictLoader(sample_catalogs), **options)


def test_loader_must_be_a_loader(make_locales_dir: MakeLocalesDir) -> None:
    not_a_loader: Any = object()
    with pytest.raises(ConfigurationError, match="Loader"):
        Localizer(loader=not_a_loader)
    with pytest.raises(ConfigurationError):
        Localizer(make_locales_dir(), loader=DictLoader({"en": {}}))
    with pytest.raises(ConfigurationError):
        Localizer()


def test_configuration_errors_are_value_errors(sample_catalogs: Catalogs) -> None:
    with pytest.raises(ValueError, match="not among"):
        Localizer(loader=DictLoader(sample_catalogs), default_locale="de")


def test_default_locale_is_normalized(sample_catalogs: Catalogs) -> None:
    l10n = Localizer(loader=DictLoader(sample_catalogs), default_locale="pt_br")
    assert l10n.default_locale == "pt-BR"


# --- preload -------------------------------------------------------------------


def test_preload_surfaces_a_broken_catalog(make_locales_dir: MakeLocalesDir) -> None:
    catalogs = {"en": {"a": "A"}, "tr": {"a": 3}}
    with pytest.raises(InvalidCatalogError) as info:
        Localizer(make_locales_dir(catalogs), preload=True)
    assert (info.value.path, info.value.pointer) == ("tr.json", "/a")
    lazy = Localizer(make_locales_dir(catalogs))
    assert lazy.t("a") == "A"
    with pytest.raises(InvalidCatalogError):
        lazy.t("a", locale="tr")


def test_preload_loads_every_locale_once(
    make_locales_dir: MakeLocalesDir, io_audit: IoAudit
) -> None:
    l10n = Localizer(make_locales_dir(), preload=True)
    l10n.t("missing", locale="İt")  # imports logging before the audit is armed
    with io_audit.watching():
        for tag in sorted(l10n.locales):
            l10n.t("nav.home", locale=tag)
    assert io_audit.events == []


# --- request-time tags (LOC-02) --------------------------------------------------

_BAD_TAGS = ["../../etc", "İt", "", "x" * 129, _tag(129), "und", "C"]


@pytest.mark.parametrize("tag", _BAD_TAGS)
def test_invalid_request_tag_falls_back_to_default(
    make_locales_dir: MakeLocalesDir, caplog: pytest.LogCaptureFixture, tag: str
) -> None:
    l10n = Localizer(make_locales_dir())
    with caplog.at_level(logging.DEBUG, logger="locjson"):
        assert l10n.t("nav.home", locale=tag) == "Home"
    records = [record for record in caplog.records if record.name == "locjson"]
    assert len(records) == 1
    assert records[0].levelno == logging.DEBUG
    assert len(records[0].getMessage()) < 200


def test_invalid_request_tags_never_touch_the_filesystem(
    make_locales_dir: MakeLocalesDir, io_audit: IoAudit
) -> None:
    l10n = Localizer(make_locales_dir())
    l10n.t("nav.home", locale="İt")  # warm-up: loads en and imports logging
    with io_audit.watching():
        for _ in range(3):
            for tag in _BAD_TAGS:
                assert l10n.t("nav.home", locale=tag) == "Home"
                assert l10n.has("nav.home", locale=tag)
            assert l10n.t("nav.home", locale="de") == "Home"
    assert io_audit.events == []


def test_audit_records_real_reads(
    make_locales_dir: MakeLocalesDir, io_audit: IoAudit
) -> None:
    l10n = Localizer(make_locales_dir())
    with io_audit.watching():
        l10n.t("nav.home", locale="tr")
    assert [event for event, _ in io_audit.events] == ["open"]
    assert io_audit.events[0][1].endswith("tr.json")


def test_tag_of_128_characters_is_accepted(sample_catalogs: Catalogs) -> None:
    sample_catalogs["en-US"] = {"nav": {"home": "Home (US)"}}
    l10n = Localizer(loader=DictLoader(sample_catalogs))
    assert len(_tag(128)) == 128
    assert l10n.t("nav.home", locale=_tag(128)) == "Home (US)"
    assert l10n.t("nav.home", locale=_tag(129)) == "Home"


def test_context_is_reserved(sample_catalogs: Catalogs) -> None:
    l10n = Localizer(loader=DictLoader(sample_catalogs))
    reserved: Any = "formal"
    with pytest.raises(LocJsonError, match="reserved"):
        l10n.t("greeting", context=reserved, name="x")
    assert l10n.t("greeting", context=None, name="x") == "Hello, x!"


# --- has() and locales (RT-02) -----------------------------------------------------


def test_has(sample_catalogs: Catalogs) -> None:
    sample_catalogs["en"].update({"blank": "", "unset": None})
    sample_catalogs["tr"]["plural_blank"] = {"one": "bir", "other": ""}
    l10n = Localizer(loader=DictLoader(sample_catalogs))
    assert l10n.has("nav.home")
    assert l10n.has("inbox.messages")
    assert not l10n.has("nav")
    assert not l10n.has("inbox")
    assert l10n.has("only_en", locale="tr")
    assert l10n.has("city", locale="tr")
    assert not l10n.has("city")
    assert not l10n.has("blank")
    assert not l10n.has("unset")
    assert not l10n.has("plural_blank", locale="tr")
    assert not l10n.has("missing")
    assert not l10n.has("")


def test_has_never_consults_the_missing_policy(sample_catalogs: Catalogs) -> None:
    l10n = Localizer(loader=DictLoader(sample_catalogs), missing="raise")
    assert not l10n.has("missing")


def test_locales_is_the_discovered_set(
    make_locales_dir: MakeLocalesDir, sample_catalogs: Catalogs
) -> None:
    l10n = Localizer(make_locales_dir())
    assert isinstance(l10n.locales, frozenset)
    assert l10n.locales == frozenset(sample_catalogs)


# --- keys ------------------------------------------------------------------------


def test_keys_are_compared_exactly() -> None:
    l10n = Localizer(
        loader=DictLoader({"en": {"nav": {"home": "Home"}, "başlık": "B"}})
    )
    assert l10n.t("nav.home") == "Home"
    assert l10n.t("nav.Home") == "nav.Home"
    assert l10n.t("başlık") == "B"
    assert l10n.has("başlık")


# --- chains --------------------------------------------------------------------------


def test_no_fallbacks_and_empty_fallbacks_give_identical_chains(
    sample_catalogs: Catalogs,
) -> None:
    none = Localizer(loader=DictLoader(sample_catalogs), fallbacks=None)
    empty = Localizer(loader=DictLoader(sample_catalogs), fallbacks={})
    for tag in ("pt-BR", "zh-Hant-TW", "en", "de-AT"):
        assert none._chain(tag) == empty._chain(tag)


def test_explicit_fallbacks_are_normalized(sample_catalogs: Catalogs) -> None:
    l10n = Localizer(
        loader=DictLoader(sample_catalogs), fallbacks={"pt_br": ("pt",), "de": []}
    )
    assert l10n._chain("pt-BR") == ("pt-BR", "pt", "en")
    assert l10n.t("nav.home", locale="pt-BR") == "Início"


def test_chain_cache_is_bounded(sample_catalogs: Catalogs) -> None:
    l10n = Localizer(loader=DictLoader(sample_catalogs))
    letters = string.ascii_lowercase
    tags = [f"{p}{a}{b}" for p in "qr" for a, b in itertools.product(letters, letters)]
    for tag in tags[:1000]:
        assert l10n.t("nav.home", locale=tag) == "Home"
        assert len(l10n._chains) <= localizer_module._CHAIN_CACHE_MAX
    assert localizer_module._CHAIN_CACHE_MAX == 256
    assert locale_module._normalize.cache_info().currsize <= 1024


def test_concurrent_lookups_with_valid_and_invalid_tags(
    sample_catalogs: Catalogs,
) -> None:
    l10n = Localizer(loader=DictLoader(sample_catalogs))
    cases = [
        ("tr", "Ana Sayfa"),
        ("../../etc", "Home"),
        ("pt-BR", "Início"),
        ("İt", "Home"),
        ("zh-TW", "首頁"),
        ("x" * 200, "Home"),
        ("en", "Home"),
    ]
    barrier = threading.Barrier(8)
    failures: list[tuple[str, str]] = []

    def worker(offset: int) -> None:
        barrier.wait()
        for index in range(200):
            tag, expected = cases[(index + offset) % len(cases)]
            got = l10n.t("nav.home", locale=tag)
            if got != expected:
                failures.append((tag, got))

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert failures == []
    assert len(l10n._chains) <= localizer_module._CHAIN_CACHE_MAX
