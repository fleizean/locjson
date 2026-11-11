"""The current locale: ``use()``, ``set_locale()`` and ``current_locale`` (RT-03)."""

from __future__ import annotations

import asyncio
import contextvars
import logging
import sys
import threading
from typing import TYPE_CHECKING, TypeVar

import pytest

from locjson import DictLoader, Localizer
from locjson.context import LocaleContext

if TYPE_CHECKING:
    from collections.abc import Callable

    from tests.conftest import Catalogs

T = TypeVar("T")
TIMEOUT = 10.0


@pytest.fixture
def l10n(sample_catalogs: Catalogs) -> Localizer:
    return Localizer(loader=DictLoader(sample_catalogs), default_locale="en")


def _in_fresh_context(function: Callable[[], T]) -> T:
    return contextvars.copy_context().run(function)


# --- use() and set_locale() ----------------------------------------------------


def test_use_switches_and_restores(l10n: Localizer) -> None:
    with l10n.use("tr") as tag:
        assert tag == "tr"
        assert l10n.t("nav.home") == "Ana Sayfa"
        assert l10n.current_locale == "tr"
    assert l10n.t("nav.home") == "Home"
    assert l10n.current_locale == "en"


def test_use_yields_the_canonical_tag(l10n: Localizer) -> None:
    with l10n.use("pt_br") as tag:
        assert tag == "pt-BR"
        assert l10n.current_locale == "pt-BR"
        assert l10n.t("nav.settings") == "Configurações"


def test_explicit_locale_wins_over_the_context(l10n: Localizer) -> None:
    with l10n.use("tr"):
        assert l10n.t("nav.home", locale="en") == "Home"
        assert l10n.has("only_en", locale="en")
        assert not l10n.has("city", locale="en")
        assert l10n.has("city")


def test_set_locale_affects_only_the_current_context(l10n: Localizer) -> None:
    def body() -> tuple[str, str]:
        assert l10n.set_locale("tr") is None  # type: ignore[func-returns-value]
        return l10n.current_locale, l10n.t("nav.home")

    assert _in_fresh_context(body) == ("tr", "Ana Sayfa")
    assert l10n.current_locale == "en"
    assert _in_fresh_context(lambda: l10n.current_locale) == "en"


def test_set_locale_is_seen_by_a_new_asyncio_task_only_inside(
    l10n: Localizer,
) -> None:
    async def main() -> tuple[str, str]:
        l10n.set_locale("tr")

        async def child() -> str:
            return l10n.current_locale

        inner = await asyncio.create_task(child())
        return l10n.current_locale, inner

    assert asyncio.run(main()) == ("tr", "tr")
    assert l10n.current_locale == "en"


def test_current_locale_defaults_when_nothing_is_set(l10n: Localizer) -> None:
    assert l10n.current_locale == "en"
    assert l10n._context.get() is None


def test_nested_use_blocks_restore_each_level(l10n: Localizer) -> None:
    seen: list[str] = []

    def middle() -> None:
        with l10n.use("pt"):
            seen.append(l10n.current_locale)
            with l10n.use("ar"):
                seen.append(l10n.current_locale)
            seen.append(l10n.current_locale)
            msg = "boom"
            raise RuntimeError(msg)

    with l10n.use("tr"):
        seen.append(l10n.current_locale)
        with pytest.raises(RuntimeError, match="boom"):
            middle()
        seen.append(l10n.current_locale)
    seen.append(l10n.current_locale)
    assert seen == ["tr", "pt", "ar", "pt", "tr", "en"]


def test_use_restores_a_value_set_with_set_locale(l10n: Localizer) -> None:
    def body() -> list[str]:
        l10n.set_locale("pt")
        with l10n.use("tr"):
            inside = l10n.current_locale
        return [inside, l10n.current_locale]

    assert _in_fresh_context(body) == ["tr", "pt"]


def test_two_localizers_keep_independent_locales(
    sample_catalogs: Catalogs, l10n: Localizer
) -> None:
    other = Localizer(loader=DictLoader(sample_catalogs), default_locale="en")
    with l10n.use("tr"):
        assert other.current_locale == "en"
        assert other.t("nav.home") == "Home"
        with other.use("ar"):
            assert l10n.current_locale == "tr"
            assert other.t("nav.home") == "الرئيسية"
            assert l10n.t("nav.home") == "Ana Sayfa"


@pytest.mark.parametrize("tag", ["not a tag!!", "", "und", "x" * 200])
def test_invalid_tag_falls_back_to_default_with_one_debug_record(
    l10n: Localizer, caplog: pytest.LogCaptureFixture, tag: str
) -> None:
    with caplog.at_level(logging.DEBUG, logger="locjson"):
        with l10n.use(tag) as effective:
            assert effective == "en"
            assert l10n.current_locale == "en"
            assert l10n._context.get() is None
        records = [r for r in caplog.records if r.name == "locjson"]
        assert len(records) == 1
        assert records[0].levelno == logging.DEBUG
        caplog.clear()

        def body() -> str:
            l10n.set_locale(tag)
            return l10n.current_locale

        assert _in_fresh_context(body) == "en"
        records = [r for r in caplog.records if r.name == "locjson"]
        assert len(records) == 1
        assert records[0].levelno == logging.DEBUG


def test_set_locale_to_an_invalid_tag_clears_a_previous_value(
    l10n: Localizer,
) -> None:
    def body() -> str | None:
        l10n.set_locale("tr")
        l10n.set_locale("not a tag!!")
        return l10n._context.get()

    assert _in_fresh_context(body) is None


def test_undiscovered_but_valid_locale_falls_back_through_the_chain(
    l10n: Localizer,
) -> None:
    with l10n.use("de-AT") as tag:
        assert tag == "de-AT"
        assert l10n.current_locale == "de-AT"
        assert l10n.t("nav.home") == "Home"


# --- isolation across asyncio tasks and threads --------------------------------


@pytest.mark.parametrize("first", ["a", "b"])
def test_asyncio_tasks_are_isolated(l10n: Localizer, first: str) -> None:
    async def main() -> dict[str, tuple[str, str]]:
        entered = {"a": asyncio.Event(), "b": asyncio.Event()}
        go = asyncio.Event()
        results: dict[str, tuple[str, str]] = {}

        async def worker(name: str, tag: str) -> None:
            if name != first:
                await entered[first].wait()
            with l10n.use(tag):
                entered[name].set()
                await go.wait()
                results[name] = (l10n.current_locale, l10n.t("nav.home"))

        tasks = [
            asyncio.create_task(worker("a", "tr")),
            asyncio.create_task(worker("b", "ar")),
        ]
        await entered["a"].wait()
        await entered["b"].wait()
        go.set()
        await asyncio.gather(*tasks)
        return results

    results = asyncio.run(main())
    assert results == {"a": ("tr", "Ana Sayfa"), "b": ("ar", "الرئيسية")}
    assert l10n.current_locale == "en"


def test_threads_are_isolated(l10n: Localizer) -> None:
    barrier = threading.Barrier(2, timeout=TIMEOUT)
    results: dict[str, tuple[str, str]] = {}

    def worker(tag: str) -> None:
        with l10n.use(tag):
            barrier.wait()  # both threads are inside their own use() block
            results[tag] = (l10n.current_locale, l10n.t("nav.home"))
            barrier.wait()  # neither leaves before both have looked up

    threads = [threading.Thread(target=worker, args=(tag,)) for tag in ("tr", "ar")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(TIMEOUT)
    assert results == {"tr": ("tr", "Ana Sayfa"), "ar": ("ar", "الرئيسية")}
    assert l10n.current_locale == "en"


def test_new_thread_inherits_only_on_free_threaded_builds(l10n: Localizer) -> None:
    seen: list[str] = []

    def body() -> None:
        l10n.set_locale("tr")
        thread = threading.Thread(target=lambda: seen.append(l10n.current_locale))
        thread.start()
        thread.join(TIMEOUT)

    _in_fresh_context(body)
    inherits = getattr(sys.flags, "thread_inherit_context", 0) == 1
    assert seen == (["tr"] if inherits else ["en"])


# --- token safety ----------------------------------------------------------------


def test_reset_from_another_context_restores_the_unset_state(
    l10n: Localizer,
) -> None:
    manager = l10n.use("tr")
    entering = contextvars.copy_context()
    assert entering.run(manager.__enter__) == "tr"
    assert entering.run(lambda: l10n.current_locale) == "tr"
    exiting = contextvars.copy_context()
    exiting.run(manager.__exit__, None, None, None)
    assert exiting.run(l10n._context.get) is None
    assert exiting.run(lambda: l10n.current_locale) == "en"


def test_reset_from_another_context_restores_the_previous_value(
    l10n: Localizer,
) -> None:
    def prepare() -> None:
        l10n.set_locale("pt")

    entering = contextvars.copy_context()
    entering.run(prepare)
    manager = l10n.use("tr")
    entering.run(manager.__enter__)
    exiting = contextvars.copy_context()
    exiting.run(manager.__exit__, None, None, None)
    assert exiting.run(lambda: l10n.current_locale) == "pt"


def test_locale_context_unit() -> None:
    context = LocaleContext()
    assert context.get() is None

    def body() -> list[str | None]:
        seen: list[str | None] = []
        context.set("tr")
        seen.append(context.get())
        with context.use("ar"):
            seen.append(context.get())
            with context.use(None):
                seen.append(context.get())
            seen.append(context.get())
        seen.append(context.get())
        return seen

    assert _in_fresh_context(body) == ["tr", "ar", None, "ar", "tr"]
    assert context.get() is None


def test_each_locale_context_has_its_own_variable() -> None:
    first, second = LocaleContext(), LocaleContext()

    def body() -> tuple[str | None, str | None]:
        first.set("tr")
        return first.get(), second.get()

    assert _in_fresh_context(body) == ("tr", None)
