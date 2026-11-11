"""Structural catalog rules enforced by ``build_catalog`` (CAT-02/03/05/07, RT-05).

Tests that need several sources of one locale build ``RawSource`` objects
directly, so they do not depend on any loader's directory layout.
"""

from __future__ import annotations

import threading
import unicodedata
from typing import TYPE_CHECKING, Any

import pytest

from locjson import DictLoader, InvalidCatalogError, Localizer, RawSource
from locjson._jsonio import read_json
from locjson.catalog import BuildResult, Catalog, Meta, build_catalog

if TYPE_CHECKING:
    from collections.abc import Sequence

    from locjson.errors import CatalogIssue

Issue = tuple[str, str, str]


def _src(
    data: object, origin: str = "en.json", namespace: str | None = None
) -> RawSource:
    return RawSource(data, origin, namespace)


def _build(*sources: RawSource, locale: str = "en") -> BuildResult:
    return build_catalog(locale, sources)


def _issues(result: BuildResult) -> list[Issue]:
    return [(i.path, i.pointer, i.problem) for i in result.issues]


def _one(result: BuildResult) -> CatalogIssue:
    assert result.catalog is None
    (issue,) = result.issues
    return issue


# --- reserved $ keys (CAT-03) --------------------------------------------------


def test_nested_meta_is_an_error_but_comment_is_ignored() -> None:
    data = {"g": {"$meta": {}, "$comment": {"any": [1, 2]}, "x": "y"}}
    issue = _one(_build(_src(data)))
    assert (issue.path, issue.pointer) == ("en.json", "/g/$meta")
    assert issue.problem == "$meta is only allowed at the top level of a file"


def test_dollar_keys_are_ignored_at_any_depth_without_validation() -> None:
    data = {
        "$comment": 1,
        "$todo": [None, 1.5],
        "g": {"$note": {"deep": {"$x": True}}, "h": {"$y": None, "x": "X"}},
    }
    catalog = _build(_src(data)).unwrap()
    assert sorted(catalog) == ["g.h.x"]


@pytest.mark.parametrize(
    ("meta", "pointer", "problem"),
    [
        pytest.param(
            "rtl", "/$meta", "$meta must be an object, got str", id="not-object"
        ),
        pytest.param(
            {"foo": 1},
            "/$meta/foo",
            "unknown $meta key 'foo'; only 'locale' and 'direction' are allowed",
            id="unknown-key",
        ),
        pytest.param(
            {"locale": "tr"},
            "/$meta/locale",
            "$meta.locale does not match the file's locale 'en'",
            id="locale-mismatch",
        ),
        pytest.param(
            {"locale": "en_US"},
            "/$meta/locale",
            "$meta.locale does not match the file's locale 'en'",
            id="locale-region",
        ),
        pytest.param(
            {"locale": "english"},
            "/$meta/locale",
            "$meta.locale is not a valid locale tag",
            id="locale-invalid",
        ),
        pytest.param(
            {"locale": 5},
            "/$meta/locale",
            "$meta.locale must be a string, got int",
            id="locale-type",
        ),
        pytest.param(
            {"direction": "up"},
            "/$meta/direction",
            "$meta.direction must be 'ltr' or 'rtl'",
            id="direction-value",
        ),
        pytest.param(
            {"direction": "RTL"},
            "/$meta/direction",
            "$meta.direction must be 'ltr' or 'rtl'",
            id="direction-case",
        ),
        pytest.param(
            {"direction": ["rtl"]},
            "/$meta/direction",
            "$meta.direction must be 'ltr' or 'rtl'",
            id="direction-type",
        ),
    ],
)
def test_invalid_meta(meta: object, pointer: str, problem: str) -> None:
    issue = _one(_build(_src({"$meta": meta, "x": "y"})))
    assert (issue.path, issue.pointer, issue.problem) == ("en.json", pointer, problem)


def test_valid_meta_is_stored_on_the_catalog() -> None:
    data = {"$meta": {"locale": "pt_br", "direction": "ltr"}, "x": "y"}
    catalog = _build(_src(data, "pt-BR.json"), locale="pt-BR").unwrap()
    assert isinstance(catalog.meta, Meta)
    assert (catalog.meta.locale, catalog.direction) == ("pt-BR", "ltr")
    assert sorted(catalog) == ["x"]


def test_meta_is_never_a_translation() -> None:
    catalog = _build(_src({"$meta": {"direction": "rtl"}, "x": "y"})).unwrap()
    assert "$meta" not in catalog
    assert "$meta.direction" not in catalog
    assert sorted(catalog) == ["x"]
    assert catalog.direction == "rtl"


def test_empty_meta_is_accepted() -> None:
    catalog = _build(_src({"$meta": {}, "x": "y"})).unwrap()
    assert (catalog.meta.locale, catalog.direction) == (None, None)


def test_file_with_only_meta_has_zero_translations() -> None:
    catalog = _build(_src({"$meta": {"direction": "rtl"}}), locale="ar").unwrap()
    assert len(catalog) == 0
    assert catalog.direction == "rtl"


def test_duplicate_meta_field_is_reported() -> None:
    data = read_json(
        b'{"$meta": {"direction": "ltr", "direction": "rtl"}}', origin="en.json"
    )
    issue = _one(_build(_src(data)))
    assert (issue.pointer, issue.problem) == (
        "/$meta/direction",
        "duplicate key 'direction'",
    )


def test_repeated_comment_keys_are_not_duplicates() -> None:
    data = read_json(b'{"$comment": "a", "$comment": "b", "x": "y"}', origin="en.json")
    assert sorted(_build(_src(data)).unwrap()) == ["x"]


def test_repeated_reserved_keys_are_duplicates() -> None:
    raw = b'{"$meta": {}, "$meta": {}, "g": {"$plural": false, "$plural": false}}'
    data = read_json(raw, origin="en.json")
    assert _issues(_build(_src(data))) == [
        ("en.json", "/$meta", "duplicate key '$meta'"),
        ("en.json", "/g/$plural", "duplicate key '$plural'"),
    ]


@pytest.mark.parametrize("value", [True, "false", 0, None, {}])
def test_plural_flag_only_accepts_false(value: object) -> None:
    issue = _one(_build(_src({"g": {"$plural": value, "x": "y"}})))
    assert (issue.pointer, issue.problem) == (
        "/g/$plural",
        "$plural only accepts false",
    )


def test_plural_false_keeps_the_group() -> None:
    data = {"g": {"$plural": False, "one": "1", "other": "n"}}
    assert sorted(_build(_src(data)).unwrap()) == ["g.one", "g.other"]


# --- $meta across namespace files (CAT-03 ordering) -----------------------------


def _ns(name: str, meta: object) -> RawSource:
    return _src({"$meta": meta, "x": "y"}, f"en/{name}.json", name)


def test_equal_meta_across_namespaces_merges() -> None:
    catalog = _build(
        _ns("a", {"direction": "ltr"}), _ns("b", {"direction": "ltr"})
    ).unwrap()
    assert catalog.direction == "ltr"
    assert sorted(catalog) == ["a.x", "b.x"]


def test_meta_from_one_namespace_applies_to_the_locale() -> None:
    catalog = _build(
        _ns("a", {}), _ns("b", {"direction": "rtl", "locale": "en"})
    ).unwrap()
    assert (catalog.meta.locale, catalog.direction) == ("en", "rtl")


@pytest.mark.parametrize("reverse", [False, True], ids=["sorted", "reversed"])
def test_conflicting_meta_across_namespaces_names_both(reverse: bool) -> None:
    sources = [_ns("a", {"direction": "ltr"}), _ns("b", {"direction": "rtl"})]
    issue = _one(_build(*(reversed(sources) if reverse else sources)))
    assert (issue.path, issue.pointer) == ("en/b.json", "/$meta/direction")
    assert (issue.other_path, issue.other_pointer) == ("en/a.json", "/$meta/direction")
    assert issue.problem == "$meta.direction 'rtl' conflicts with 'ltr'"
    assert issue.locale == "en"


# --- key paths (CAT-02) ----------------------------------------------------------


@pytest.mark.parametrize(
    "reverse", [False, True], ids=["literal-first", "nested-first"]
)
def test_literal_dotted_key_collides_with_nested_key(reverse: bool) -> None:
    items: list[tuple[str, object]] = [("a.b", "x"), ("a", {"b": "y"})]
    data = dict(reversed(items) if reverse else items)
    issue = _one(_build(_src(data)))
    assert {issue.pointer, issue.other_pointer} == {"/a.b", "/a/b"}
    assert (issue.pointer, issue.other_pointer) == ("/a/b", "/a.b")
    assert (issue.path, issue.other_path) == ("en.json", "en.json")
    assert issue.problem == "key 'a.b' is defined more than once"


def test_collision_is_raised_with_both_locations() -> None:
    result = _build(_src({"a.b": "x", "a": {"b": "y"}}))
    with pytest.raises(InvalidCatalogError) as info:
        result.unwrap()
    error = info.value
    assert (error.path, error.pointer) == ("en.json", "/a/b")
    assert (error.other_path, error.other_pointer) == ("en.json", "/a.b")
    assert str(error) == (
        "en.json: /a/b: key 'a.b' is defined more than once "
        "(conflicts with en.json: /a.b)"
    )


@pytest.mark.parametrize(
    ("key", "pointer"),
    [("", "/"), (".a", "/.a"), ("a.", "/a."), ("a..b", "/a..b")],
)
def test_empty_key_segment(key: str, pointer: str) -> None:
    issue = _one(_build(_src({key: "x", "ok": "y"})))
    assert issue.pointer == pointer
    assert issue.problem == f"empty key segment in key '{key}'"


def test_empty_key_segment_in_nested_object() -> None:
    issue = _one(_build(_src({"g": {"": "x"}})))
    assert (issue.pointer, issue.problem) == ("/g/", "empty key segment in key ''")


def test_dollar_segment_inside_a_dotted_key_is_reserved() -> None:
    issue = _one(_build(_src({"a.$meta": "x"})))
    assert issue.pointer == "/a.$meta"
    assert (
        issue.problem
        == "key segment '$meta' in key 'a.$meta' starts with '$', which is reserved"
    )


@pytest.mark.parametrize(
    ("data", "pointer", "other_pointer", "problem"),
    [
        pytest.param(
            {"a.b": "x", "a": {"b": {"c": "y"}}},
            "/a/b/c",
            "/a.b",
            "key 'a.b.c' is nested under 'a.b', which is a translation",
            id="literal-translation",
        ),
        pytest.param(
            {"a": {"b": "x"}, "a.b.c": "y"},
            "/a.b.c",
            "/a/b",
            "key 'a.b.c' is nested under 'a.b', which is a translation",
            id="literal-group",
        ),
        pytest.param(
            {"a": "x", "a.b": "y"},
            "/a.b",
            "/a",
            "key 'a.b' is nested under 'a', which is a translation",
            id="top-level",
        ),
    ],
)
def test_prefix_conflict_names_both(
    data: dict[str, object], pointer: str, other_pointer: str, problem: str
) -> None:
    issue = _one(_build(_src(data)))
    assert (issue.pointer, issue.other_pointer, issue.problem) == (
        pointer,
        other_pointer,
        problem,
    )
    assert issue.other_path == "en.json"


def test_prefix_conflict_across_files() -> None:
    result = _build(_src({"a": "x"}, "en.json"), _src({"a": {"b": "y"}}, "en2.json"))
    issue = _one(result)
    assert (issue.path, issue.pointer) == ("en2.json", "/a/b")
    assert (issue.other_path, issue.other_pointer) == ("en.json", "/a")


def test_same_key_from_two_namespaces_is_distinct() -> None:
    a = _src({"x": "1"}, "en/a.json", "a")
    b = _src({"x": "2"}, "en/b.json", "b")
    catalog = _build(a, b).unwrap()
    assert {key: catalog[key].source for key in catalog} == {"a.x": "1", "b.x": "2"}


@pytest.mark.parametrize("reverse", [False, True], ids=["sorted", "reversed"])
def test_same_key_from_two_plain_sources_collides(reverse: bool) -> None:
    sources = [
        _src({"x": "1"}, "en.json"),
        _src({"g": {"h": None}, "x": "2"}, "en2.json"),
    ]
    issue = _one(_build(*(reversed(sources) if reverse else sources)))
    assert (issue.path, issue.pointer) == ("en2.json", "/x")
    assert (issue.other_path, issue.other_pointer) == ("en.json", "/x")
    assert issue.problem == "key 'x' is defined more than once"


def test_namespace_prefixes_dotted_keys() -> None:
    catalog = _build(
        _src({"a.b": "x", "c": {"d": "y"}}, "en/common.json", "common")
    ).unwrap()
    assert sorted(catalog) == ["common.a.b", "common.c.d"]


# --- empty leaves and encoding (CAT-05) ------------------------------------------


def test_empty_and_null_leaves_are_not_stored_but_space_is() -> None:
    catalog = _build(_src({"empty": "", "null": None, "space": " "})).unwrap()
    assert sorted(catalog) == ["space"]
    assert catalog["space"].render({}) == " "


def test_all_empty_file_builds_an_empty_catalog() -> None:
    result = _build(_src({"a": "", "b": None, "g": {"c": "", "h": {"d": None}}}))
    assert result.issues == ()
    assert result.catalog is not None
    assert len(result.catalog) == 0


def test_empty_and_null_fall_through_but_space_does_not() -> None:
    loader = DictLoader(
        {
            "en": {"a": "A", "b": "B", "c": "C"},
            "tr": {"a": "", "b": None, "c": " "},
        }
    )
    l10n = Localizer(loader=loader)
    assert [l10n.t(key, locale="tr") for key in "abc"] == ["A", "B", " "]


def test_all_empty_locale_falls_through() -> None:
    loader = DictLoader(
        {"en": {"a": "A", "g": {"b": "B"}}, "tr": {"a": "", "g": {"b": None}}}
    )
    l10n = Localizer(loader=loader)
    assert (l10n.t("a", locale="tr"), l10n.t("g.b", locale="tr")) == ("A", "B")


def test_keys_are_not_unicode_normalized() -> None:
    nfc = unicodedata.normalize("NFC", "café")
    nfd = unicodedata.normalize("NFD", "café")
    assert nfc != nfd
    catalog = _build(_src({nfc: "composed", nfd: "decomposed"})).unwrap()
    assert len(catalog) == 2
    assert catalog[nfc].source == "composed"
    assert catalog[nfd].source == "decomposed"


def test_values_are_stored_exactly_as_decoded() -> None:
    nfd = unicodedata.normalize("NFD", "Işık İstanbul")
    catalog = _build(_src({"x": nfd})).unwrap()
    assert catalog["x"].render({}) == nfd


# --- deterministic issues and atomic results (CAT-05, RT-05) ---------------------


def _messy(order: Sequence[str]) -> dict[str, object]:
    values: dict[str, object] = {
        "n": 1,
        "a.b": "x",
        "a": {"b": "y", "f": 1.5},
        "": "e",
        "z": {"$meta": {}},
        "t": "{0}",
    }
    return {key: values[key] for key in order}


def test_issues_are_sorted_regardless_of_key_and_source_order() -> None:
    keys = ["n", "a.b", "a", "", "z", "t"]
    first = _build(_src(_messy(keys)), _src({"n": True}, "de.json"))
    second = _build(_src({"n": True}, "de.json"), _src(_messy(keys[::-1])))
    assert first.issues == second.issues
    paths_pointers = [(i.path, i.pointer, i.problem) for i in first.issues]
    assert paths_pointers == sorted(paths_pointers)
    assert [i.pointer for i in first.issues] == [
        "/n",
        "/",
        "/a/b",
        "/a/f",
        "/n",
        "/t",
        "/z/$meta",
    ]


def test_result_is_all_or_nothing() -> None:
    bad = _build(_src({"good": "fine", "bad": 1}))
    assert bad.catalog is None
    assert len(bad.issues) == 1
    good = _build(_src({"good": "fine"}))
    assert good.issues == ()
    assert isinstance(good.catalog, Catalog)


def test_whole_document_error_omits_the_pointer() -> None:
    with pytest.raises(InvalidCatalogError) as info:
        _build(_src(["not", "an", "object"])).unwrap()
    assert info.value.pointer == ""
    assert (
        str(info.value) == "en.json: expected a JSON object at the top level, got list"
    )


def test_error_from_several_issues_reports_the_first() -> None:
    result = _build(
        _src({"z": 1, "a": True}, "fr.json"),
        _src({"m": [1]}, "de.json"),
        locale="de",
    )
    with pytest.raises(InvalidCatalogError) as info:
        result.unwrap()
    error = info.value
    assert (error.path, error.pointer) == ("de.json", "/m")
    assert (
        str(error) == "de.json: /m: expected a string or object, got list (and 2 more)"
    )
    assert [(i.path, i.pointer) for i in error.issues] == [
        ("de.json", "/m"),
        ("fr.json", "/a"),
        ("fr.json", "/z"),
    ]


# --- immutability and concurrency (CAT-02, CAT-07) -------------------------------


def test_catalog_is_immutable() -> None:
    catalog = _build(
        _src({"$meta": {"direction": "rtl"}, "x": "y"}), locale="ar"
    ).unwrap()
    target: Any = catalog
    with pytest.raises(AttributeError):
        target.extra = 1
    with pytest.raises(AttributeError):
        target._entries = {}
    with pytest.raises(AttributeError):
        target.meta._direction = "ltr"
    for name in (
        "__setitem__",
        "__delitem__",
        "pop",
        "popitem",
        "clear",
        "update",
        "setdefault",
    ):
        assert not hasattr(catalog, name)
    with pytest.raises(TypeError):
        target["x"] = "z"


def test_build_is_pure_and_thread_safe() -> None:
    data = {
        "$meta": {"direction": "rtl"},
        "greeting": "Merhaba, {name}!",
        "nav": {"home": "Ana Sayfa", "a.b": "c"},
    }
    sources = (_src(data, "tr.json"),)
    results: list[Catalog] = []
    errors: list[BaseException] = []

    def build() -> None:
        try:
            results.extend(build_catalog("tr", sources).unwrap() for _ in range(50))
        except BaseException as exc:  # noqa: BLE001 - re-raised in the main thread
            errors.append(exc)

    threads = [threading.Thread(target=build) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == []
    assert len(results) == 100
    expected = build_catalog("tr", sources).unwrap()
    for catalog in results:
        assert (
            sorted(catalog) == sorted(expected) == ["greeting", "nav.a.b", "nav.home"]
        )
        assert catalog["greeting"].render({"name": "Işık"}) == "Merhaba, Işık!"
        assert catalog.direction == "rtl"
    assert data == {
        "$meta": {"direction": "rtl"},
        "greeting": "Merhaba, {name}!",
        "nav": {"home": "Ana Sayfa", "a.b": "c"},
    }
