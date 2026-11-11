"""The module-level API: ``locjson.setup()`` and its delegating functions (RT-06)."""

from __future__ import annotations

import contextvars
import threading
from typing import TYPE_CHECKING

import pytest

import locjson
from locjson import (
    ConfigurationError,
    DictLoader,
    Localizer,
    LocJsonError,
)
from locjson import locale as locale_module

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from pathlib import Path

    from tests.conftest import Catalogs

TIMEOUT = 30.0

PUBLIC = {
    "ConfigurationError",
    "DictLoader",
    "FilesystemLoader",
    "InterpolationError",
    "InvalidCatalogError",
    "InvalidLocaleError",
    "LocJsonError",
    "Loader",
    "Localizer",
    "MissingTranslationError",
    "RawSource",
    "__version__",
    "direction",
    "get_localizer",
    "has",
    "negotiate",
    "set_locale",
    "setup",
    "t",
    "use",
}


@pytest.fixture(autouse=True)
def _no_default_localizer() -> Iterator[None]:
    locjson._DEFAULT.localizer = None
    yield
    locjson._DEFAULT.localizer = None


@pytest.mark.parametrize(
    "call",
    [
        locjson.get_localizer,
        lambda: locjson.t("nav.home"),
        lambda: locjson.has("nav.home"),
        lambda: locjson.use("tr"),
        lambda: locjson.set_locale("tr"),
    ],
    ids=["get_localizer", "t", "has", "use", "set_locale"],
)
def test_calls_before_setup_raise(call: Callable[[], object]) -> None:
    with pytest.raises(LocJsonError, match=r"^call locjson\.setup\(\) first$"):
        call()


def test_setup_installs_and_returns_the_default(sample_catalogs: Catalogs) -> None:
    l10n = locjson.setup(loader=DictLoader(sample_catalogs), default_locale="en")
    assert isinstance(l10n, Localizer)
    assert locjson.get_localizer() is l10n
    assert l10n.default_locale == "en"


def test_setup_passes_every_option(sample_catalogs: Catalogs) -> None:
    l10n = locjson.setup(
        loader=DictLoader(sample_catalogs),
        default_locale="tr",
        fallbacks={"pt-BR": ["pt"]},
        missing="empty",
        preload=True,
    )
    assert l10n.default_locale == "tr"
    assert locjson.t("nav.home") == "Ana Sayfa"
    assert locjson.t("nav.home", locale="pt-BR") == "Início"
    assert locjson.t("no.such.key") == ""
    assert set(l10n._snapshot.catalogs) == l10n.locales


def test_setup_with_a_path(tmp_path: Path) -> None:
    (tmp_path / "en.json").write_text('{"hello": "Hello"}', encoding="utf-8")
    locjson.setup(tmp_path)
    assert locjson.t("hello") == "Hello"


def test_second_setup_replaces_the_default(sample_catalogs: Catalogs) -> None:
    first = locjson.setup(loader=DictLoader(sample_catalogs))
    second = locjson.setup(loader=DictLoader(sample_catalogs), default_locale="tr")
    assert second is not first
    assert locjson.get_localizer() is second
    assert locjson.t("nav.home") == "Ana Sayfa"


def test_failed_setup_keeps_the_previous_default(
    sample_catalogs: Catalogs, tmp_path: Path
) -> None:
    first = locjson.setup(loader=DictLoader(sample_catalogs))
    with pytest.raises(ConfigurationError):
        locjson.setup(tmp_path / "missing")
    assert locjson.get_localizer() is first
    with pytest.raises(ConfigurationError):
        locjson.setup(loader=DictLoader(sample_catalogs), default_locale="de")
    assert locjson.get_localizer() is first


def test_functions_delegate_to_the_default(sample_catalogs: Catalogs) -> None:
    l10n = locjson.setup(loader=DictLoader(sample_catalogs))
    assert locjson.t("greeting", name="Enes") == "Hello, Enes!"
    assert locjson.t("inbox.messages", locale="tr", count=1) == "1 mesajınız var"
    assert locjson.has("only_en")
    assert not locjson.has("city")
    assert locjson.has("city", locale="tr")
    with locjson.use("tr") as tag:
        assert tag == "tr"
        assert l10n.current_locale == "tr"
        assert locjson.t("nav.home") == "Ana Sayfa"
        assert locjson.has("city")
    assert locjson.t("nav.home") == "Home"

    def body() -> tuple[str, str]:
        locjson.set_locale("ar")
        return l10n.current_locale, locjson.t("nav.home")

    assert contextvars.copy_context().run(body) == ("ar", "الرئيسية")
    assert l10n.current_locale == "en"


def test_negotiate_and_direction_are_the_pure_functions() -> None:
    assert locjson.negotiate is locale_module.negotiate
    assert locjson.direction is locale_module.direction
    assert locjson.negotiate("tr-TR,tr;q=0.9", ["en", "tr"], "en") == "tr"
    assert locjson.direction("he") == "rtl"


def test_concurrent_setup_never_leaves_the_default_unset(
    sample_catalogs: Catalogs,
) -> None:
    locjson.setup(loader=DictLoader(sample_catalogs))
    stop = threading.Event()
    started = threading.Event()
    seen: set[str] = set()

    def reader() -> None:
        while not stop.is_set():
            seen.add(locjson.t("nav.home"))
            started.set()

    thread = threading.Thread(target=reader)
    thread.start()
    try:
        assert started.wait(TIMEOUT)
        for _ in range(100):
            locjson.setup(loader=DictLoader(sample_catalogs))
    finally:
        stop.set()
        thread.join(TIMEOUT)
    assert not thread.is_alive()
    assert seen == {"Home"}


# --- the public surface (PKG-02) ------------------------------------------------


def test_all_is_the_documented_public_surface() -> None:
    assert len(locjson.__all__) == len(set(locjson.__all__))
    assert set(locjson.__all__) == PUBLIC
    for name in locjson.__all__:
        assert hasattr(locjson, name), name


@pytest.mark.parametrize("name", sorted(PUBLIC - {"__version__"}))
def test_every_export_is_documented(name: str) -> None:
    doc = getattr(locjson, name).__doc__
    assert isinstance(doc, str)
    assert doc.strip()


def test_no_module_level_getattr() -> None:
    assert "__getattr__" not in vars(locjson)
