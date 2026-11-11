"""Plural entries: CAT-04 detection, PLUR-03 selection and PLUR-04 ``{count}``."""

from __future__ import annotations

import importlib
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest

from locjson import DictLoader, InvalidCatalogError, Localizer, RawSource
from locjson._jsonio import read_json
from locjson.catalog import build_catalog
from locjson.formatting import compile_template
from locjson.plural.categories import CATEGORIES, CATEGORY_SET, PluralEntry
from locjson.plural.resolver import default_resolver, select_form

if TYPE_CHECKING:
    from collections.abc import Mapping

    from locjson.formatting import Template
    from tests.conftest import Catalogs, MakeLocalesDir

localizer_module = importlib.import_module("locjson.localizer")


def _entry(**forms: str) -> PluralEntry:
    return PluralEntry({name: compile_template(text) for name, text in forms.items()})


def _l10n(
    catalogs: Mapping[str, Mapping[str, object]], default: str = "en"
) -> Localizer:
    return Localizer(loader=DictLoader(catalogs), default_locale=default)


def _issues(data: object) -> list[tuple[str, str]]:
    result = build_catalog("en", [RawSource(data, "en.json")])
    return [(issue.pointer, issue.problem) for issue in result.issues]


# --- the sample catalogs (ROADMAP SC2) ---------------------------------------


def test_sample_messages_pick_zero_one_other(make_locales_dir: MakeLocalesDir) -> None:
    l10n = Localizer(make_locales_dir())
    assert l10n.t("inbox.messages", count=0) == "You have no messages"
    assert l10n.t("inbox.messages", count=1) == "You have 1 message"
    assert l10n.t("inbox.messages", count=3) == "You have 3 messages"
    assert l10n.t("inbox.messages", locale="tr", count=0) == "Hiç mesajınız yok"
    assert l10n.t("inbox.messages", locale="tr", count=5) == "5 mesajınız var"


def test_without_count_the_other_form_is_used(sample_catalogs: Catalogs) -> None:
    assert _l10n(sample_catalogs).t("inbox.messages") == "You have {count} messages"


# --- selection (PLUR-03) ----------------------------------------------------


@pytest.mark.parametrize(
    ("count", "expected"),
    [
        (0, "o:0"),
        (1, "1:1"),
        (-1, "1:-1"),
        (2, "o:2"),
        (1.0, "1:1.0"),
        (2.5, "o:2.5"),
        (Decimal(1), "1:1"),
        (Decimal("2.50"), "o:2.50"),
        (1.5, "o:1.5"),
    ],
)
def test_one_other_without_zero(count: float | Decimal, expected: str) -> None:
    l10n = _l10n({"en": {"x": {"one": "1:{count}", "other": "o:{count}"}}})
    assert l10n.t("x", count=count) == expected


@pytest.mark.parametrize("count", [0, 0.0, Decimal(0), Decimal("0.00")])
def test_explicit_zero_override(count: float | Decimal) -> None:
    l10n = _l10n({"en": {"x": {"zero": "none", "one": "one", "other": "{count}"}}})
    assert l10n.t("x", count=count) == "none"


def test_zero_override_applies_in_any_language() -> None:
    l10n = _l10n({"en": {"x": "-"}, "tr": {"x": {"zero": "hiç", "other": "{count}"}}})
    assert l10n.t("x", locale="tr", count=0) == "hiç"
    assert l10n.t("x", locale="tr", count=1) == "1"


def test_count_renders_without_rounding() -> None:
    l10n = _l10n({"en": {"x": {"one": "one", "other": "{count} items"}}})
    assert l10n.t("x", count=0) == "0 items"
    assert l10n.t("x", count=1.5) == "1.5 items"
    assert l10n.t("x", count=Decimal("2.50")) == "2.50 items"


def test_form_is_chosen_by_category_not_json_order() -> None:
    forward = _l10n({"en": {"x": {"one": "single", "other": "many"}}})
    backward = _l10n({"en": {"x": {"other": "many", "one": "single"}}})
    for count in (0, 1, 2):
        assert forward.t("x", count=count) == backward.t("x", count=count)
    assert backward.t("x", count=1) == "single"


def test_empty_form_counts_as_absent() -> None:
    l10n = _l10n({"en": {"x": {"one": "", "other": "o"}}})
    assert l10n.t("x", count=1) == "o"
    zero = _l10n({"en": {"x": {"zero": "", "other": "o{count}"}}})
    assert zero.t("x", count=0) == "o0"


def test_empty_other_is_untranslated_and_falls_through() -> None:
    l10n = _l10n(
        {
            "en": {"x": {"one": "en one", "other": "en other"}},
            "tr": {"x": {"other": "", "one": "tr one"}},
        }
    )
    assert l10n.t("x", locale="tr", count=1) == "en one"
    assert l10n.t("x", locale="tr", count=4) == "en other"


def test_count_fills_plain_strings_too(sample_catalogs: Catalogs) -> None:
    l10n = _l10n(sample_catalogs)
    assert l10n.t("greeting", count=2, name="X") == "Hello, X!"
    plain = _l10n({"en": {"n": "{count} left"}})
    assert plain.t("n", count=2) == "2 left"


def test_rules_follow_the_supplying_catalog(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str] = []

    def spy(entry: PluralEntry, locale: str, count: float | Decimal) -> Template:
        seen.append(locale)
        return select_form(entry, locale, count)

    monkeypatch.setattr(localizer_module, "select_form", spy)
    l10n = _l10n({"en": {"x": {"one": "one", "other": "other"}}, "tr": {}})
    assert l10n.t("x", locale="tr", count=1) == "one"
    assert seen == ["en"]


def test_select_form_passes_the_catalog_locale_to_the_resolver() -> None:
    calls: list[tuple[str, object]] = []

    def resolver(locale: str, count: float | Decimal) -> str:
        calls.append((locale, count))
        return "few"

    entry = _entry(zero="z", few="f", other="o")
    assert select_form(entry, "pl", 3, resolver).source == "f"
    assert select_form(entry, "pl", 0, resolver).source == "z"
    assert calls == [("pl", 3)]
    missing = _entry(other="o")
    assert select_form(missing, "pl", 3, resolver).source == "o"


@pytest.mark.parametrize(
    ("count", "category"),
    [(1, "one"), (-1, "one"), (1.0, "one"), (Decimal(1), "one"), (0, "other")],
)
def test_default_resolver(count: float | Decimal, category: str) -> None:
    assert default_resolver("en", count) == category
    assert default_resolver("en", 2) == "other"


# --- the data model ----------------------------------------------------------


def test_categories_are_in_cldr_order() -> None:
    assert CATEGORIES == ("zero", "one", "two", "few", "many", "other")
    assert frozenset(CATEGORIES) == CATEGORY_SET


def test_plural_entry_is_immutable_and_exposes_its_forms() -> None:
    entry = _entry(other="{n} of {count}", one="{count}")
    assert list(entry.forms) == ["one", "other"]
    assert entry.other.source == "{n} of {count}"
    assert entry.get("one") is not None
    assert entry.get("few") is None
    assert entry.fields == frozenset({"n", "count"})
    assert entry == _entry(one="{count}", other="{n} of {count}")
    assert entry != _entry(other="x")
    assert entry != "x"
    assert hash(entry) == hash(_entry(one="{count}", other="{n} of {count}"))
    assert "PluralEntry" in repr(entry)
    with pytest.raises(AttributeError):
        entry._other = compile_template("x")
    with pytest.raises(TypeError):
        entry.forms["two"] = compile_template("x")  # type: ignore[index]


def test_plural_entry_requires_other_and_categories() -> None:
    with pytest.raises(ValueError, match="other"):
        PluralEntry({"one": compile_template("x")})
    with pytest.raises(ValueError, match="category"):
        PluralEntry({"other": compile_template("x"), "lots": compile_template("y")})


# --- detection (CAT-04) ------------------------------------------------------


def test_plural_object_becomes_one_entry() -> None:
    catalog = build_catalog(
        "en", [RawSource({"x": {"one": "a", "other": "b"}}, "en.json")]
    ).unwrap()
    assert list(catalog) == ["x"]
    assert isinstance(catalog["x"], PluralEntry)


def test_plural_false_reads_categories_as_a_group() -> None:
    data = {"x": {"one": "a", "other": "b", "$plural": False}}
    catalog = build_catalog("en", [RawSource(data, "en.json")]).unwrap()
    assert sorted(catalog) == ["x.one", "x.other"]
    l10n = _l10n({"en": data})
    assert (l10n.t("x.one"), l10n.t("x.other")) == ("a", "b")


def test_category_object_without_other_is_an_error() -> None:
    assert _issues({"x": {"one": "a", "two": "b"}}) == [
        ("/x", "plural entry has no 'other' form")
    ]
    with pytest.raises(InvalidCatalogError, match="no 'other' form"):
        _l10n({"en": {"x": {"one": "a", "two": "b"}}}).t("x")


@pytest.mark.parametrize("value", [3, None, True, ["a"], {"k": "v"}])
def test_category_object_with_a_non_string_value_is_an_error(value: object) -> None:
    issues = _issues({"x": {"one": "a", "other": value}})
    assert len(issues) == 1
    pointer, problem = issues[0]
    assert pointer == "/x/other"
    assert "looks like a plural entry" in problem
    assert '"$plural": false' in problem


def test_empty_object_contributes_no_keys() -> None:
    catalog = build_catalog("en", [RawSource({"x": {}}, "en.json")]).unwrap()
    assert len(catalog) == 0


def test_mixed_keys_are_a_group() -> None:
    data = {"x": {"one": "a", "other": "b", "label": "c"}}
    catalog = build_catalog("en", [RawSource(data, "en.json")]).unwrap()
    assert sorted(catalog) == ["x.label", "x.one", "x.other"]


def test_annotations_inside_a_plural_are_ignored() -> None:
    data = {"x": {"$comment": "note", "one": "a", "other": "b"}}
    catalog = build_catalog("en", [RawSource(data, "en.json")]).unwrap()
    assert list(catalog) == ["x"]


def test_reserved_keys_inside_a_plural_are_still_checked() -> None:
    assert _issues({"x": {"$plural": True, "one": "a", "other": "b"}}) == [
        ("/x/$plural", "$plural only accepts false")
    ]
    assert _issues({"x": {"$meta": {}, "other": "b"}}) == [
        ("/x/$meta", "$meta is only allowed at the top level of a file")
    ]


def test_invalid_form_template_is_reported_at_the_form() -> None:
    issues = _issues({"x": {"one": "{count!r}", "other": "ok"}})
    assert [pointer for pointer, _ in issues] == ["/x/one"]
    assert _issues({"x": {"one": "a", "other": "\ud800"}}) == [
        ("/x/other", "lone surrogate in value")
    ]


def test_plural_and_literal_child_key_conflict() -> None:
    data = {
        "inbox": {"messages": {"one": "a", "other": "b"}},
        "inbox.messages.one": "c",
    }
    issues = _issues(data)
    assert len(issues) == 1
    assert "nested under 'inbox.messages'" in issues[0][1]


def test_same_plural_from_two_sources_collides() -> None:
    forms = {"one": "a", "other": "b"}
    result = build_catalog(
        "en",
        [
            RawSource({"x": forms}, "en/a.json", "ns"),
            RawSource({"x": {"other": "c"}}, "en/b.json", "ns"),
        ],
    )
    assert [issue.problem for issue in result.issues] == [
        "key 'ns.x' is defined more than once"
    ]


def test_duplicate_forms_are_reported() -> None:
    data = read_json(b'{"x": {"one": "a", "one": "b", "other": "c"}}', origin="en.json")
    assert _issues(data) == [("/x/one", "duplicate key 'one'")]
