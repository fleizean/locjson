"""Lazy, once-per-locale loading and an I/O-free warm path (CAT-08, RT-01)."""

from __future__ import annotations

import collections
import threading
from typing import TYPE_CHECKING

import pytest

from locjson import DictLoader, InvalidCatalogError, Localizer
from locjson._compat import override

if TYPE_CHECKING:
    from collections.abc import Mapping

    from locjson import RawSource
    from tests.conftest import Catalogs, IoAudit, MakeLocalesDir

TIMEOUT = 30.0


class CountingLoader(DictLoader):
    """A DictLoader that counts ``load()`` calls per locale."""

    __slots__ = ("calls", "lock")

    def __init__(self, catalogs: Mapping[str, Mapping[str, object]]) -> None:
        super().__init__(catalogs)
        self.calls: collections.Counter[str] = collections.Counter()
        self.lock = threading.Lock()

    @override
    def load(self, locale: str) -> tuple[RawSource, ...]:
        with self.lock:
            self.calls[locale] += 1
        return super().load(locale)


def test_only_requested_locales_load_and_each_once(
    sample_catalogs: Catalogs,
) -> None:
    loader = CountingLoader(sample_catalogs)
    l10n = Localizer(loader=loader)
    assert loader.calls == {}
    for index in range(1000):
        locale = "tr" if index % 2 else "en"
        l10n.t("nav.home", locale=locale)
        l10n.t("greeting", locale=locale, name="Enes")
    assert loader.calls == {"en": 1, "tr": 1}
    for tag in ("pt", "pt-BR", "zh", "zh-Hant", "ar"):
        assert loader.calls[tag] == 0
    assert set(l10n._snapshot.catalogs) == {"en", "tr"}


def test_repeated_calls_are_identical(sample_catalogs: Catalogs) -> None:
    loader = CountingLoader(sample_catalogs)
    l10n = Localizer(loader=loader)
    first = l10n.t("inbox.messages", locale="tr", count=3)
    second = l10n.t("inbox.messages", locale="tr", count=3)
    assert first == second == "3 mesajınız var"
    assert loader.calls == {"tr": 1}


def test_a_fallback_locale_loads_only_when_needed(sample_catalogs: Catalogs) -> None:
    loader = CountingLoader(sample_catalogs)
    l10n = Localizer(loader=loader, fallbacks={"pt-BR": ["pt"]})
    assert l10n.t("nav.settings", locale="pt-BR") == "Configurações"
    assert loader.calls == {"pt-BR": 1}
    assert l10n.t("nav.home", locale="pt-BR") == "Início"
    assert loader.calls == {"pt-BR": 1, "pt": 1}


def test_cold_start_from_eight_threads_loads_once(sample_catalogs: Catalogs) -> None:
    loader = CountingLoader(sample_catalogs)
    l10n = Localizer(loader=loader)
    barrier = threading.Barrier(8, timeout=TIMEOUT)
    results: list[str] = []
    results_lock = threading.Lock()

    def worker() -> None:
        barrier.wait()
        text = l10n.t("nav.home", locale="tr")
        with results_lock:
            results.append(text)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(TIMEOUT)
    assert results == ["Ana Sayfa"] * 8
    assert loader.calls["tr"] == 1


def test_load_skips_locales_already_loaded_or_gone(sample_catalogs: Catalogs) -> None:
    loader = CountingLoader(sample_catalogs)
    l10n = Localizer(loader=loader)
    l10n._load("tr")
    l10n._load("tr")
    l10n._load("de")
    assert loader.calls == {"tr": 1}
    assert set(l10n._snapshot.catalogs) == {"tr"}


def test_a_broken_locale_does_not_poison_the_others(
    make_locales_dir: MakeLocalesDir,
) -> None:
    root = make_locales_dir()
    (root / "tr.json").write_text('{"nav": {"home": ', encoding="utf-8")
    l10n = Localizer(root)
    with pytest.raises(InvalidCatalogError):
        l10n.t("nav.home", locale="tr")
    assert l10n.t("nav.home") == "Home"
    assert l10n.t("nav.home", locale="ar") == "الرئيسية"
    with pytest.raises(InvalidCatalogError):
        l10n.t("nav.home", locale="tr")
    assert "tr" not in l10n._snapshot.catalogs
    assert set(l10n._snapshot.catalogs) == {"en", "ar"}


def test_warm_lookups_do_no_file_io(
    make_locales_dir: MakeLocalesDir, io_audit: IoAudit
) -> None:
    l10n = Localizer(make_locales_dir(), fallbacks={"pt-BR": ["pt"]})

    def lookups() -> list[object]:
        return [
            l10n.t("nav.home"),
            l10n.t("greeting", name="Enes"),
            l10n.t("nav.home", locale="tr"),
            l10n.t("inbox.messages", locale="tr", count=1),
            l10n.t("city", locale="tr"),
            l10n.t("nav.home", locale="tr-TR"),
            l10n.has("nav.home", locale="tr"),
            l10n.t("missing.key", locale="tr"),
            l10n.t("greeting", locale="tr"),
            l10n.current_locale,
        ]

    expected = lookups()
    with l10n.use("tr"):
        lookups()
    with io_audit.watching():
        for _ in range(1000):
            assert lookups() == expected
            with l10n.use("tr"):
                assert l10n.t("nav.home") == "Ana Sayfa"
    assert io_audit.events == []
    assert set(l10n._snapshot.catalogs) == {"en", "tr"}
