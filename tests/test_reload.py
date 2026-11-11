"""``Localizer.reload()``: all-or-nothing, atomic catalog swaps (RT-07)."""

from __future__ import annotations

import json
import threading
from typing import TYPE_CHECKING

import pytest

from locjson import (
    ConfigurationError,
    DictLoader,
    InvalidCatalogError,
    Localizer,
    RawSource,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator, Mapping
    from pathlib import Path

    from tests.conftest import Catalogs, MakeLocalesDir

TIMEOUT = 30.0


def _write(root: Path, tag: str, data: Mapping[str, object]) -> None:
    text = json.dumps(data, ensure_ascii=False, indent=2)
    (root / f"{tag}.json").write_text(text, encoding="utf-8")


class VersionedLoader:
    """Serves one version of every locale; discovery picks the version.

    ``discover_locales()`` captures :attr:`version`, and ``load()`` serves the
    captured version, so a lazy load always matches the latest discovery.
    """

    def __init__(self, versions: list[dict[str, dict[str, object]]]) -> None:
        self.versions = versions
        self.version = 0
        self.served = 0
        self.discoveries = 0
        self.loads: list[tuple[int, str]] = []

    def discover_locales(self) -> frozenset[str]:
        self.discoveries += 1
        self.served = self.version
        return frozenset(self.versions[self.served])

    def load(self, locale: str) -> tuple[RawSource, ...]:
        self.loads.append((self.served, locale))
        data = self.versions[self.served][locale]
        return (RawSource(data, f"<v{self.served}>/{locale}"),)


V1: dict[str, dict[str, object]] = {"en": {"K": "en-v1"}, "tr": {"K": "tr-v1"}}
V2: dict[str, dict[str, object]] = {"en": {"K": "en-v2"}, "tr": {"other": "x"}}


# --- content changes -----------------------------------------------------------


def test_reload_serves_edited_text(
    make_locales_dir: MakeLocalesDir, sample_catalogs: Catalogs
) -> None:
    root = make_locales_dir()
    l10n = Localizer(root)
    assert l10n.t("nav.home", locale="tr") == "Ana Sayfa"
    sample_catalogs["tr"]["nav"] = {"home": "Anasayfa", "settings": "Ayarlar"}
    _write(root, "tr", sample_catalogs["tr"])
    assert l10n.t("nav.home", locale="tr") == "Ana Sayfa"  # no I/O until reload
    l10n.reload()
    assert l10n.t("nav.home", locale="tr") == "Anasayfa"


def test_half_written_file_keeps_the_old_catalogs(
    make_locales_dir: MakeLocalesDir,
) -> None:
    root = make_locales_dir()
    l10n = Localizer(root)
    assert l10n.t("nav.home", locale="tr") == "Ana Sayfa"
    assert l10n.t("nav.home") == "Home"
    before = l10n.locales
    (root / "tr.json").write_text('{"nav": {"home": "Anasa', encoding="utf-8")
    with pytest.raises(InvalidCatalogError):
        l10n.reload()
    assert l10n.t("nav.home", locale="tr") == "Ana Sayfa"
    assert l10n.t("nav.home") == "Home"
    assert l10n.locales == before


def test_invalid_utf8_keeps_the_old_catalogs(make_locales_dir: MakeLocalesDir) -> None:
    root = make_locales_dir()
    l10n = Localizer(root)
    assert l10n.t("city", locale="tr") == "İstanbul'da ılık bir akşam"
    (root / "tr.json").write_bytes(b'{"city": "\xff"}')
    with pytest.raises(InvalidCatalogError):
        l10n.reload()
    assert l10n.t("city", locale="tr") == "İstanbul'da ılık bir akşam"


def test_failed_reload_then_fixed_file_reloads(
    make_locales_dir: MakeLocalesDir, sample_catalogs: Catalogs
) -> None:
    root = make_locales_dir()
    l10n = Localizer(root)
    l10n.t("nav.home", locale="tr")
    (root / "tr.json").write_text("{", encoding="utf-8")
    with pytest.raises(InvalidCatalogError):
        l10n.reload()
    sample_catalogs["tr"]["greeting"] = "Selam, {name}!"
    _write(root, "tr", sample_catalogs["tr"])
    l10n.reload()
    assert l10n.t("greeting", locale="tr", name="Enes") == "Selam, Enes!"


def test_added_and_removed_locales(
    make_locales_dir: MakeLocalesDir,
) -> None:
    root = make_locales_dir()
    l10n = Localizer(root)
    assert l10n.t("nav.home", locale="ar") == "الرئيسية"
    assert "de" not in l10n.locales
    _write(root, "de", {"nav": {"home": "Startseite"}})
    (root / "ar.json").unlink()
    l10n.reload()
    assert "de" in l10n.locales
    assert "ar" not in l10n.locales
    assert l10n.t("nav.home", locale="de") == "Startseite"
    assert l10n.t("nav.home", locale="ar") == "Home"
    assert "ar" not in l10n._snapshot.catalogs


def test_unchanged_files_give_identical_results(
    make_locales_dir: MakeLocalesDir,
) -> None:
    l10n = Localizer(make_locales_dir(), fallbacks={"pt-BR": ["pt"]})

    def results() -> list[str]:
        return [
            l10n.t("greeting", name="Enes"),
            l10n.t("nav.home", locale="pt-BR"),
            l10n.t("nav.home", locale="zh-TW"),
            l10n.t("inbox.messages", locale="tr", count=3),
            l10n.t("braces", name="x"),
        ]

    before = results()
    loaded = set(l10n._snapshot.catalogs)
    l10n.reload()
    assert results() == before
    assert set(l10n._snapshot.catalogs) == loaded


def test_reload_rebuilds_only_loaded_locales() -> None:
    loader = VersionedLoader([V1, V2])
    l10n = Localizer(loader=loader)
    assert l10n.t("K") == "en-v1"
    loader.version = 1
    loader.loads.clear()
    l10n.reload()
    assert loader.loads == [(1, "en")]
    assert l10n.t("K") == "en-v2"
    assert set(l10n._snapshot.catalogs) == {"en"}


def test_reload_of_a_fresh_localizer_only_rediscovers() -> None:
    loader = VersionedLoader([V1, V2])
    l10n = Localizer(loader=loader)
    l10n.reload()
    assert loader.discoveries == 2
    assert loader.loads == []
    assert dict(l10n._snapshot.catalogs) == {}


def test_reload_with_preload_builds_every_locale(
    make_locales_dir: MakeLocalesDir,
) -> None:
    root = make_locales_dir()
    l10n = Localizer(root, preload=True)
    _write(root, "de", {"nav": {"home": "Startseite"}})
    l10n.reload()
    assert set(l10n._snapshot.catalogs) == l10n.locales
    assert "de" in l10n._snapshot.catalogs


def test_reload_with_preload_is_all_or_nothing(
    make_locales_dir: MakeLocalesDir,
) -> None:
    root = make_locales_dir()
    l10n = Localizer(root, preload=True)
    (root / "zh.json").write_text("[1, 2", encoding="utf-8")
    with pytest.raises(InvalidCatalogError):
        l10n.reload()
    assert l10n.t("nav.home", locale="zh") == "首页"


def test_missing_default_locale_keeps_the_old_state(
    make_locales_dir: MakeLocalesDir,
) -> None:
    root = make_locales_dir()
    l10n = Localizer(root)
    assert l10n.t("nav.home") == "Home"
    before = l10n.locales
    (root / "en.json").unlink()
    with pytest.raises(ConfigurationError, match="default_locale"):
        l10n.reload()
    assert l10n.locales == before
    assert l10n.t("nav.home") == "Home"


def test_discovery_error_keeps_the_old_state(
    make_locales_dir: MakeLocalesDir,
) -> None:
    root = make_locales_dir()
    l10n = Localizer(root)
    assert l10n.t("nav.home") == "Home"
    before = l10n.locales
    _write(root, "common", {})
    with pytest.raises(InvalidCatalogError, match="common"):
        l10n.reload()
    assert l10n.locales == before
    assert l10n.t("nav.home") == "Home"


def test_reload_keeps_the_context_locale(sample_catalogs: Catalogs) -> None:
    l10n = Localizer(loader=DictLoader(sample_catalogs))
    with l10n.use("tr"):
        assert l10n.t("nav.home") == "Ana Sayfa"
        l10n.reload()
        assert l10n.t("nav.home") == "Ana Sayfa"


# --- atomicity -------------------------------------------------------------------


class _ReloadingChain(tuple[str, ...]):
    """A fallback chain that runs ``action`` once, just before yielding ``at``.

    It makes a reload land deterministically between a reader taking its
    snapshot and the reader lazily loading a later locale of the chain.
    """

    action: Callable[[], None] | None = None
    at = ""

    def __iter__(self) -> Iterator[str]:
        for tag in tuple.__iter__(self):
            if tag == self.at and self.action is not None:
                action, self.action = self.action, None
                action()
            yield tag


def test_lazy_load_after_a_reload_restarts_from_the_new_snapshot() -> None:
    loader = VersionedLoader([V1, V2])
    loader.version = 1
    l10n = Localizer(loader=loader)
    assert l10n.t("other", locale="tr") == "x"  # tr v2 loaded, en still cold

    def reload_to_v1() -> None:
        loader.version = 0
        l10n.reload()

    chain = _ReloadingChain(("tr", "en"))
    chain.at = "en"
    chain.action = reload_to_v1
    l10n._chains["tr"] = chain
    # The reader saw tr v2 (no K) and needs en, but a reload to v1 lands first.
    # Mixing the old tr with a freshly loaded en would give "en-v1".
    assert l10n.t("K", locale="tr") == "tr-v1"
    assert chain.action is None


def test_has_after_a_reload_restarts_from_the_new_snapshot() -> None:
    loader = VersionedLoader([V1, V2])
    loader.version = 1
    l10n = Localizer(loader=loader)
    l10n.t("other", locale="tr")

    def reload_to_v1() -> None:
        loader.version = 0
        l10n.reload()

    chain = _ReloadingChain(("tr", "en"))
    chain.at = "en"
    chain.action = reload_to_v1
    l10n._chains["tr"] = chain
    assert l10n.has("K", locale="tr")
    assert l10n.t("K", locale="tr") == "tr-v1"


def test_lazy_load_of_a_locale_removed_by_a_reload_is_skipped() -> None:
    v1: dict[str, dict[str, object]] = {"en": {"K": "en"}, "tr": {"K": "tr"}}
    v2: dict[str, dict[str, object]] = {"en": {"K": "en"}}
    loader = VersionedLoader([v1, v2])
    l10n = Localizer(loader=loader)
    l10n.t("K")

    def drop_tr() -> None:
        loader.version = 1
        l10n.reload()

    chain = _ReloadingChain(("tr", "en"))
    chain.at = "tr"
    chain.action = drop_tr
    l10n._chains["tr"] = chain
    assert l10n.t("K", locale="tr") == "en"
    assert (1, "tr") not in loader.loads


@pytest.mark.parametrize("warm_en", [True, False], ids=["en-warm", "en-cold"])
def test_readers_never_see_a_mixed_generation(warm_en: bool) -> None:
    loader = VersionedLoader([V1, V2])
    l10n = Localizer(loader=loader)
    if warm_en:
        assert l10n.t("K") == "en-v1"
    seen: set[str] = set()
    stop = threading.Event()
    started = threading.Event()

    def reader() -> None:
        while not stop.is_set():
            seen.add(l10n.t("K", locale="tr"))
            started.set()

    thread = threading.Thread(target=reader)
    thread.start()
    try:
        assert started.wait(TIMEOUT)
        for round_ in range(200):
            loader.version = (round_ + 1) % 2
            l10n.reload()
    finally:
        stop.set()
        thread.join(TIMEOUT)
    assert not thread.is_alive()
    assert seen
    assert "en-v1" not in seen
    assert seen <= {"tr-v1", "en-v2"}
