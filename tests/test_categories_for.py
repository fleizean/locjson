"""``categories_for(locale)``: the plural categories a locale needs (PLUR-06)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

import locjson
from locjson import InvalidLocaleError, plural
from locjson.plural import resolver
from locjson.plural.categories import CATEGORIES
from locjson.plural.resolver import _lookup, rule_for

if TYPE_CHECKING:
    from collections.abc import Iterator

FIXTURE_PATH = Path(__file__).parent / "data" / "cldr49_plural_samples.json"
FIXTURE = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
SAMPLES: dict[str, dict[str, list[str]]] = FIXTURE["samples"]
PT_PT_CHILDREN: list[str] = FIXTURE["pt_pt_children"]
ALL_SIX = frozenset(CATEGORIES)
ONE_OTHER = frozenset({"one", "other"})


@pytest.fixture(autouse=True)
def _fresh_rule_cache() -> Iterator[None]:
    _lookup.cache_clear()
    yield
    _lookup.cache_clear()


@pytest.fixture
def hidden_babel(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "babel", None)


def test_russian_needs_one_few_many_other() -> None:
    assert plural.categories_for("ru") == frozenset({"one", "few", "many", "other"})


@pytest.mark.parametrize("tag", sorted(SAMPLES))
def test_builtin_categories_match_the_cldr_fixture(tag: str) -> None:
    assert plural.categories_for(tag) == frozenset(SAMPLES[tag])


@pytest.mark.parametrize("tag", PT_PT_CHILDREN)
def test_pt_pt_children_share_the_pt_pt_categories(tag: str) -> None:
    assert plural.categories_for(tag) == frozenset(SAMPLES["pt-PT"])


def test_a_single_category_locale() -> None:
    assert plural.categories_for("ja") == frozenset({"other"})


@pytest.mark.usefixtures("hidden_babel")
def test_unknown_language_without_babel_is_one_other() -> None:
    assert plural.categories_for("xx") == ONE_OTHER


def test_unknown_language_with_babel_is_one_other() -> None:
    pytest.importorskip("babel")
    assert plural.categories_for("xx") == ONE_OTHER


def test_welsh_with_babel_has_all_six_categories() -> None:
    pytest.importorskip("babel")
    assert plural.categories_for("cy") == ALL_SIX


@pytest.mark.usefixtures("hidden_babel")
def test_welsh_without_babel_is_one_other() -> None:
    assert plural.categories_for("cy") == ONE_OTHER


@pytest.mark.parametrize("tag", ["en", "ru", "ar", "ja", "pt-PT", "xx", "cy", "lv"])
def test_every_result_is_a_frozenset_with_other(tag: str) -> None:
    result = plural.categories_for(tag)
    assert isinstance(result, frozenset)
    assert "other" in result
    assert result <= ALL_SIX


def test_spellings_of_one_tag_agree() -> None:
    expected = plural.categories_for("pt-PT")
    assert plural.categories_for("pt_PT") == expected
    assert plural.categories_for("PT-pt") == expected


def test_pt_and_pt_pt_share_categories_but_not_rules() -> None:
    assert plural.categories_for("pt") == plural.categories_for("pt-PT")
    assert plural.categories_for("pt") == frozenset({"one", "many", "other"})
    assert rule_for("pt") is not rule_for("pt-PT")


@pytest.mark.parametrize("tag", ["", "und", "x" * 129, "İt", None])
def test_invalid_tags_raise(tag: object) -> None:
    with pytest.raises(InvalidLocaleError):
        plural.categories_for(tag)


def test_callers_order_the_set_with_categories() -> None:
    ordered = sorted(plural.categories_for("ar"), key=CATEGORIES.index)
    assert ordered == ["zero", "one", "two", "few", "many", "other"]


def test_public_at_both_paths() -> None:
    assert locjson.categories_for is plural.categories_for
    assert plural.categories_for is resolver.categories_for
    assert "categories_for" in locjson.__all__
    assert "categories_for" in plural.__all__
    assert plural.categories_for.__doc__
