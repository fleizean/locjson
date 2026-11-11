"""Loader-variant invariant: every Loader drives the same Localizer identically.

Plan 01-02 promoted the :class:`~locjson.Loader` protocol to the primary
abstraction. This module holds that promise: the filesystem in both layouts,
:class:`~locjson.DictLoader` and a custom class that only implements the
protocol all produce the same ``t()`` results for the same content (CAT-09).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from locjson import DictLoader, FilesystemLoader, Loader, Localizer, RawSource

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from tests.conftest import Catalogs, MakeLocalesDir

    # Each factory returns the loader and the key prefix its layout adds.
    Factory = Callable[[Catalogs, MakeLocalesDir], tuple[Loader, str]]


class _TupleLoader:
    """A custom loader backed by ``(tag, document)`` pairs.

    It implements :class:`~locjson.Loader` structurally, without inheriting
    from it, the way a YAML, TOML or database loader would.
    """

    def __init__(self, pairs: tuple[tuple[str, Mapping[str, object]], ...]) -> None:
        self.pairs = pairs

    def discover_locales(self) -> frozenset[str]:
        return frozenset(tag for tag, _ in self.pairs)

    def load(self, locale: str) -> tuple[RawSource, ...]:
        return tuple(
            RawSource(data, f"<tuple>/{tag}")
            for tag, data in self.pairs
            if tag == locale
        )


def _single(catalogs: Catalogs, make_locales_dir: MakeLocalesDir) -> tuple[Loader, str]:
    return FilesystemLoader(make_locales_dir(catalogs)), ""


def _namespaced(
    catalogs: Catalogs, make_locales_dir: MakeLocalesDir
) -> tuple[Loader, str]:
    root = make_locales_dir(catalogs, layout="namespaced", namespace="common")
    return FilesystemLoader(root), "common."


def _dict(catalogs: Catalogs, make_locales_dir: MakeLocalesDir) -> tuple[Loader, str]:
    del make_locales_dir
    return DictLoader(catalogs), ""


def _custom(catalogs: Catalogs, make_locales_dir: MakeLocalesDir) -> tuple[Loader, str]:
    del make_locales_dir
    return _TupleLoader(tuple(catalogs.items())), ""


FACTORIES: dict[str, Factory] = {
    "filesystem-single": _single,
    "filesystem-namespaced": _namespaced,
    "dict": _dict,
    "custom": _custom,
}

# (key, locale, variables) -> expected text, identical for every variant.
# None means a missing key, which renders as the (prefixed) key itself.
EXPECTED: tuple[tuple[tuple[str, str, dict[str, Any]], str | None], ...] = (
    (("greeting", "tr", {"name": "Enes"}), "Merhaba, Enes!"),
    (("greeting", "en", {"name": "Enes"}), "Hello, Enes!"),
    (("nav.home", "tr", {}), "Ana Sayfa"),
    (("nav.home", "pt-BR", {}), "Início"),
    (("braces", "tr", {"name": "Enes"}), "Use {name} to write Enes"),
    (("city", "tr", {}), "İstanbul'da ılık bir akşam"),
    (("only_en", "tr", {}), "English only"),
    (("absent", "tr", {}), None),
)


@pytest.fixture(params=sorted(FACTORIES))
def variant(
    request: pytest.FixtureRequest,
    sample_catalogs: Catalogs,
    make_locales_dir: MakeLocalesDir,
) -> tuple[Loader, str]:
    factory = FACTORIES[request.param]
    return factory(sample_catalogs, make_locales_dir)


def _results(loader: Loader, prefix: str) -> list[str]:
    l10n = Localizer(loader=loader, fallbacks={"pt-BR": ["pt"]})
    return [
        l10n.t(prefix + key, locale=locale, **variables)
        for (key, locale, variables), _ in EXPECTED
    ]


def _expected(prefix: str) -> list[str]:
    return [prefix + key if text is None else text for (key, _, _), text in EXPECTED]


def test_every_variant_is_a_loader(variant: tuple[Loader, str]) -> None:
    loader, _ = variant
    assert isinstance(loader, Loader)


def test_every_variant_gives_the_same_results(variant: tuple[Loader, str]) -> None:
    loader, prefix = variant
    assert _results(loader, prefix) == _expected(prefix)


def test_every_variant_discovers_the_same_locales(
    variant: tuple[Loader, str], sample_catalogs: Catalogs
) -> None:
    loader, _ = variant
    assert Localizer(loader=loader).locales == frozenset(sample_catalogs)


def test_all_variants_agree(
    sample_catalogs: Catalogs, make_locales_dir: MakeLocalesDir
) -> None:
    outcomes = {
        name: _results(*factory(sample_catalogs, make_locales_dir))
        for name, factory in FACTORIES.items()
    }
    # Missing keys echo the requested key, so compare found translations only.
    found = {
        name: [text for text, (_, want) in zip(texts, EXPECTED, strict=True) if want]
        for name, texts in outcomes.items()
    }
    assert len({tuple(texts) for texts in found.values()}) == 1


def test_custom_loader_drives_the_localizer() -> None:
    loader = _TupleLoader((("en", {"greeting": "Hello, {name}!"}),))
    assert isinstance(loader, Loader)
    assert Localizer(loader=loader).t("greeting", name="Enes") == "Hello, Enes!"


def test_custom_loader_data_still_goes_through_validation() -> None:
    loader = _TupleLoader((("en", {"count": 3}),))
    l10n = Localizer(loader=loader)
    with pytest.raises(ValueError, match="<tuple>/en"):
        l10n.t("count")
