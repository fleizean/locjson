"""Bound translators: ``for_locale()`` and ``scope()`` (RT-08)."""

from __future__ import annotations

import json
import logging
import threading
from typing import TYPE_CHECKING

import pytest

from locjson import (
    ConfigurationError,
    DictLoader,
    Localizer,
    LocJsonError,
    MissingTranslationError,
    RawSource,
    Translator,
)
from locjson import translator as translator_module
from locjson._compat import override

if TYPE_CHECKING:
    from tests.conftest import Catalogs, MakeLocalesDir

TIMEOUT = 30.0


@pytest.fixture
def l10n(sample_catalogs: Catalogs) -> Localizer:
    return Localizer(loader=DictLoader(sample_catalogs), fallbacks={"pt-BR": ["pt"]})


# --- for_locale() ----------------------------------------------------------------


def test_for_locale_translates_without_touching_the_context(l10n: Localizer) -> None:
    tr = l10n.for_locale("tr")
    assert isinstance(tr, Translator)
    assert l10n.current_locale == "en"
    assert tr("nav.home") == "Ana Sayfa"
    assert tr("greeting", name="Enes") == "Merhaba, Enes!"
    assert l10n.current_locale == "en"
    assert l10n._context.get() is None
    assert l10n.t("nav.home") == "Home"


def test_bound_locale_ignores_the_current_locale(l10n: Localizer) -> None:
    tr = l10n.for_locale("tr")
    with l10n.use("ar"):
        assert tr("nav.home") == "Ana Sayfa"
        assert tr.has("city")
        assert l10n.current_locale == "ar"
        assert l10n.t("nav.home") == "الرئيسية"


def test_for_locale_normalizes_once(l10n: Localizer) -> None:
    bound = l10n.for_locale("pt_br")
    assert bound.locale == "pt-BR"
    assert bound("nav.settings") == "Configurações"
    assert bound("nav.home") == "Início"


def test_explicit_locale_overrides_the_bound_one(l10n: Localizer) -> None:
    tr = l10n.for_locale("tr")
    assert tr("nav.home", locale="ar") == "الرئيسية"
    assert tr.has("only_en", locale="en")
    assert not tr.has("city", locale="en")


def test_invalid_bound_locale_falls_back_to_the_default(
    l10n: Localizer, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.DEBUG, logger="locjson"):
        bound = l10n.for_locale("not a tag!!")
        assert bound.locale == "en"
        assert bound("nav.home") == "Home"
        assert bound("nav.home") == "Home"
    records = [r for r in caplog.records if r.name == "locjson"]
    assert len(records) == 1
    assert records[0].levelno == logging.DEBUG


def test_bound_translator_passes_count_and_context(l10n: Localizer) -> None:
    tr = l10n.for_locale("tr")
    assert tr("inbox.messages", count=0) == "Hiç mesajınız yok"
    assert tr("inbox.messages", count=2) == "2 mesajınız var"
    with pytest.raises(LocJsonError, match="reserved"):
        tr("nav.home", context="menu")  # type: ignore[arg-type]


def test_strict_localizer_stays_strict_through_a_translator(
    sample_catalogs: Catalogs,
) -> None:
    l10n = Localizer(loader=DictLoader(sample_catalogs), strict=True)
    with pytest.raises(MissingTranslationError):
        l10n.for_locale("tr")("no.such.key")
    with pytest.raises(MissingTranslationError):
        l10n.scope("nav")("nothing")


def test_t_is_an_alias_of_call(l10n: Localizer) -> None:
    tr = l10n.for_locale("tr")
    assert tr.t("nav.home") == tr("nav.home") == "Ana Sayfa"
    assert Translator.t is Translator.__call__


# --- scope() ---------------------------------------------------------------------


def test_scope_prefixes_keys(l10n: Localizer) -> None:
    inbox = l10n.scope("inbox")
    for count in (0, 1, 3):
        assert inbox("messages", count=count) == l10n.t("inbox.messages", count=count)
    assert inbox.prefix == "inbox"
    assert inbox.locale is None
    assert l10n.scope("nav").has("home")
    assert not l10n.scope("nav").has("nav.home")


def test_scope_follows_the_current_locale(l10n: Localizer) -> None:
    nav = l10n.scope("nav")
    assert nav("home") == "Home"
    with l10n.use("tr"):
        assert nav("home") == "Ana Sayfa"


def test_scope_and_for_locale_compose_in_any_order(l10n: Localizer) -> None:
    first = l10n.scope("inbox").for_locale("tr")
    second = l10n.for_locale("tr").scope("inbox")
    assert (first.locale, first.prefix) == (second.locale, second.prefix)
    assert (first.locale, first.prefix) == ("tr", "inbox")
    for count in (0, 1, 3):
        assert first("messages", count=count) == second("messages", count=count)
    assert first("messages", count=3) == "3 mesajınız var"


def test_nested_scopes_join_with_a_dot(l10n: Localizer) -> None:
    nested = l10n.scope("a").scope("b")
    assert nested.prefix == "a.b"
    assert l10n.scope("nav").for_locale("tr").scope("x").prefix == "nav.x"


def test_for_locale_on_a_translator_rebinds_and_keeps_the_prefix(
    l10n: Localizer,
) -> None:
    nav = l10n.scope("nav").for_locale("tr").for_locale("ar")
    assert (nav.locale, nav.prefix) == ("ar", "nav")
    assert nav("home") == "الرئيسية"
    fallback = l10n.scope("nav").for_locale("not a tag!!")
    assert fallback.locale == "en"


@pytest.mark.parametrize(
    "prefix",
    ["", ".a", "a.", "a..b", "$x", "a.$b", "."],
    ids=[
        "empty",
        "lead-dot",
        "trail-dot",
        "empty-seg",
        "dollar",
        "inner-dollar",
        "dot",
    ],
)
def test_invalid_prefixes_raise(l10n: Localizer, prefix: str) -> None:
    with pytest.raises(ConfigurationError, match="prefix"):
        l10n.scope(prefix)
    with pytest.raises(ConfigurationError, match="prefix"):
        l10n.for_locale("tr").scope(prefix)
    with pytest.raises(ConfigurationError, match="prefix"):
        Translator(l10n, prefix=prefix)


def test_non_string_prefix_raises(l10n: Localizer) -> None:
    with pytest.raises(ConfigurationError, match="prefix"):
        l10n.scope(3)  # type: ignore[arg-type]


# --- the object itself -----------------------------------------------------------


def test_translators_are_immutable(l10n: Localizer) -> None:
    tr = l10n.for_locale("tr")
    with pytest.raises(AttributeError):
        tr._locale = "ar"
    with pytest.raises(AttributeError):
        tr.extra = 1
    with pytest.raises(AttributeError):
        del tr._prefix
    with pytest.raises(AttributeError):
        tr.locale = "ar"  # type: ignore[misc]
    assert tr.locale == "tr"


def test_repr_shows_locale_and_prefix_without_a_lookup(
    sample_catalogs: Catalogs,
) -> None:
    calls: list[str] = []

    class Spy(DictLoader):
        @override
        def load(self, locale: str) -> tuple[RawSource, ...]:
            calls.append(locale)
            return super().load(locale)

    l10n = Localizer(loader=Spy(sample_catalogs))
    assert repr(l10n.scope("inbox").for_locale("tr")) == (
        "Translator(locale='tr', prefix='inbox')"
    )
    assert repr(l10n.for_locale("ar")) == "Translator(locale='ar', prefix=None)"
    assert repr(Translator(l10n)) == "Translator(locale=None, prefix=None)"
    assert calls == []


def test_direct_construction(l10n: Localizer) -> None:
    plain = Translator(l10n)
    assert plain("nav.home") == "Home"
    assert Translator(l10n, locale="tr", prefix="nav")("home") == "Ana Sayfa"


def test_translator_module_does_not_import_the_localizer_at_runtime() -> None:
    assert "Localizer" not in vars(translator_module)


# --- concurrency and reload ------------------------------------------------------


def test_bound_translators_in_eight_threads(l10n: Localizer) -> None:
    expected = {
        "en": "Home",
        "tr": "Ana Sayfa",
        "ar": "الرئيسية",
        "pt": "Início",
        "pt-BR": "Início",
        "zh": "首页",
        "zh-Hant": "首頁",
        "zh-TW": "首頁",
    }
    nav = l10n.scope("nav")
    barrier = threading.Barrier(len(expected), timeout=TIMEOUT)
    results: dict[str, list[str]] = {}
    lock = threading.Lock()

    def worker(tag: str) -> None:
        bound = nav.for_locale(tag)
        barrier.wait()
        seen = [bound("home") for _ in range(200)]
        with lock:
            results[tag] = seen

    threads = [threading.Thread(target=worker, args=(tag,)) for tag in expected]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(TIMEOUT)
    assert results == {tag: [text] * 200 for tag, text in expected.items()}
    assert l10n.current_locale == "en"


def test_existing_translator_sees_reloaded_catalogs(
    make_locales_dir: MakeLocalesDir, sample_catalogs: Catalogs
) -> None:
    root = make_locales_dir()
    l10n = Localizer(root)
    tr = l10n.for_locale("tr").scope("nav")
    assert tr("home") == "Ana Sayfa"
    sample_catalogs["tr"]["nav"] = {"home": "Anasayfa"}
    text = json.dumps(sample_catalogs["tr"], ensure_ascii=False)
    (root / "tr.json").write_text(text, encoding="utf-8")
    l10n.reload()
    assert tr("home") == "Anasayfa"
