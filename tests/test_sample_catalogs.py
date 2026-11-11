"""ROADMAP SC2 and the runtime half of SC5, end to end, in both layouts."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

import pytest

import locjson
from locjson import Localizer

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from tests.conftest import MakeLocalesDir

SAMPLE_LOCALES = frozenset({"en", "tr", "pt", "pt-BR", "zh", "zh-Hant", "ar"})

LAYOUTS = pytest.mark.parametrize(
    ("layout", "prefix"),
    [("single", ""), ("namespaced", "common.")],
    ids=["single", "namespaced"],
)


@pytest.fixture(autouse=True)
def _no_default_localizer() -> Iterator[None]:
    locjson._DEFAULT.localizer = None
    yield
    locjson._DEFAULT.localizer = None


def _check_sc2(t: Callable[..., str], prefix: str) -> None:
    assert t(prefix + "greeting", name="Enes") == "Hello, Enes!"
    # pt-BR has no nav.home: pt-BR -> pt -> en.
    assert t(prefix + "nav.home", locale="pt_BR") == "Início"
    assert t(prefix + "nav.settings", locale="pt_BR") == "Configurações"
    # zh-TW -> zh-Hant -> en, never plain zh.
    assert t(prefix + "nav.home", locale="zh-TW") == "首頁"
    assert t(prefix + "nav.settings", locale="zh-TW") == "Settings"
    assert t(prefix + "braces", name="Enes") == "Use {name} to write Enes"
    assert t(prefix + "inbox.messages", count=0) == "You have no messages"
    assert t(prefix + "inbox.messages", count=1) == "You have 1 message"
    assert t(prefix + "inbox.messages", count=3) == "You have 3 messages"
    assert t(prefix + "city", locale="tr") == "İstanbul'da ılık bir akşam"


def _make(
    make_locales_dir: MakeLocalesDir, layout: Literal["single", "namespaced"]
) -> Localizer:
    root = make_locales_dir(layout=layout)
    return Localizer(path=root, default_locale="en", fallbacks={"pt-BR": ["pt"]})


@LAYOUTS
def test_sc2_through_a_localizer(
    make_locales_dir: MakeLocalesDir,
    layout: Literal["single", "namespaced"],
    prefix: str,
) -> None:
    l10n = _make(make_locales_dir, layout)
    _check_sc2(l10n.t, prefix)
    assert l10n.has(prefix + "nav.home")
    assert not l10n.has(prefix + "nav")
    assert not l10n.has(prefix + "city")
    assert l10n.has(prefix + "city", locale="tr")
    assert l10n.locales == SAMPLE_LOCALES


@LAYOUTS
def test_sc5_negotiate_direction_and_use(
    make_locales_dir: MakeLocalesDir,
    layout: Literal["single", "namespaced"],
    prefix: str,
) -> None:
    l10n = _make(make_locales_dir, layout)
    assert l10n.negotiate("tr-TR,tr;q=0.9,en;q=0.8") == "tr"
    assert l10n.negotiate("de-DE,fr;q=0.5") == "en"
    assert l10n.negotiate(None) == "en"
    assert l10n.negotiate(";;;garbage") == "en"
    assert l10n.direction("ar") == "rtl"
    assert l10n.direction("ar-EG") == "rtl"
    assert l10n.direction("he") == "rtl"  # no catalog: the built-in table
    assert l10n.direction("tr") == "ltr"
    assert l10n.direction() == "ltr"
    with l10n.use(l10n.negotiate("tr-TR,tr;q=0.9,en;q=0.8")):
        assert l10n.t(prefix + "nav.home") == "Ana Sayfa"
        assert l10n.direction() == "ltr"
    with l10n.use("ar"):
        assert l10n.direction() == "rtl"
        assert l10n.t(prefix + "nav.home") == "الرئيسية"


@LAYOUTS
def test_sc2_through_the_module_api(
    make_locales_dir: MakeLocalesDir,
    layout: Literal["single", "namespaced"],
    prefix: str,
) -> None:
    root = make_locales_dir(layout=layout)
    l10n = locjson.setup(path=root, default_locale="en", fallbacks={"pt-BR": ["pt"]})
    _check_sc2(locjson.t, prefix)
    assert locjson.has(prefix + "nav.home")
    assert not locjson.has(prefix + "nav")
    assert l10n.locales == SAMPLE_LOCALES
    with locjson.use("tr"):
        assert locjson.t(prefix + "nav.home") == "Ana Sayfa"
    assert locjson.direction("ar") == "rtl"
    negotiated = locjson.negotiate("tr-TR,tr;q=0.9,en;q=0.8", l10n.locales, "en")
    assert negotiated == "tr"


def test_direction_meta_wins_over_the_table(
    make_locales_dir: MakeLocalesDir,
) -> None:
    root = make_locales_dir(
        {
            "en": {"x": "x"},
            "he": {"$meta": {"direction": "ltr"}, "x": "x"},
            "fa": {"x": "x"},
        }
    )
    l10n = Localizer(root)
    assert l10n.direction("he") == "ltr"
    assert l10n.direction("he-IL") == "ltr"
    assert l10n.direction("fa") == "rtl"
    assert l10n.direction("not a tag!!") == "ltr"
