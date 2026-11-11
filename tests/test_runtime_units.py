"""Unit tests for every seam the runtime tracer added, grouped by module."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from locjson import (
    ConfigurationError,
    DictLoader,
    FilesystemLoader,
    InterpolationError,
    InvalidCatalogError,
    InvalidLocaleError,
    Loader,
    Localizer,
    LocJsonError,
    MissingTranslationError,
    RawSource,
)
from locjson._compat import override
from locjson._jsonio import escape_pointer_token, read_json
from locjson.catalog import BuildResult, Catalog, Meta, build_catalog
from locjson.errors import CatalogIssue
from locjson.formatting import TemplateError, compile_template
from locjson.locale import fallback_chain, normalize

if TYPE_CHECKING:
    from pathlib import Path

    from tests.conftest import Catalogs, MakeLocalesDir


# --- errors -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("error", "builtin"),
    [
        (ConfigurationError, ValueError),
        (InvalidLocaleError, ValueError),
        (InvalidCatalogError, ValueError),
        (InterpolationError, ValueError),
        (MissingTranslationError, LookupError),
    ],
)
def test_error_hierarchy(error: type[Exception], builtin: type[Exception]) -> None:
    assert issubclass(error, LocJsonError)
    assert issubclass(error, builtin)


def test_missing_translation_error_is_lookup_error_not_key_error() -> None:
    error = MissingTranslationError("nav.home", "tr")
    assert isinstance(error, LookupError)
    assert not isinstance(error, KeyError)
    assert (error.key, error.locale) == ("nav.home", "tr")
    assert "nav.home" in str(error)


def test_interpolation_error_and_invalid_locale_error_attributes() -> None:
    error = InterpolationError("greeting", "name")
    assert (error.key, error.name) == ("greeting", "name")
    assert "{name}" in str(error)
    assert InvalidLocaleError(42).tag == 42


def test_catalog_issue_format_without_pointer() -> None:
    issue = CatalogIssue("en.json", "", "file is not valid UTF-8")
    assert issue.format() == "en.json: file is not valid UTF-8"


def test_catalog_issue_format_with_pointer() -> None:
    issue = CatalogIssue("en.json", "/nav/home", "bad value", "en")
    assert issue.format() == "en.json: /nav/home: bad value"
    assert issue.locale == "en"


def test_catalog_issue_format_with_other_path() -> None:
    with_pointer = CatalogIssue("en.json", "/a.b", "dup", other_path="en.json")
    with_pointer = with_pointer._replace(other_pointer="/a/b")
    assert with_pointer.format() == "en.json: /a.b: dup (conflicts with en.json: /a/b)"
    without_pointer = CatalogIssue(
        "pt-BR.json", "", "collision", other_path="pt_BR.json"
    )
    assert (
        without_pointer.format() == "pt-BR.json: collision (conflicts with pt_BR.json)"
    )
    assert isinstance(without_pointer, tuple)


def test_invalid_catalog_error_fields_and_message() -> None:
    error = InvalidCatalogError("bad", path="en.json", pointer="/x", locale="en")
    assert str(error) == "en.json: /x: bad"
    assert (error.problem, error.path, error.pointer, error.locale) == (
        "bad",
        "en.json",
        "/x",
        "en",
    )
    assert error.issues == (CatalogIssue("en.json", "/x", "bad", "en"),)


def test_from_issues_reports_first_issue_and_count() -> None:
    issues = (
        CatalogIssue("tr.json", "/a", "third"),
        CatalogIssue("en.json", "/b", "second"),
        CatalogIssue("en.json", "/a", "first"),
    )
    error = InvalidCatalogError.from_issues(issues)
    assert str(error) == "en.json: /a: first (and 2 more)"
    assert (error.path, error.pointer) == ("en.json", "/a")
    assert error.issues == issues


def test_from_issues_requires_an_issue() -> None:
    with pytest.raises(ValueError, match="at least one issue"):
        InvalidCatalogError.from_issues(())


# --- _jsonio ----------------------------------------------------------------


def test_read_json_rejects_invalid_utf8() -> None:
    with pytest.raises(InvalidCatalogError) as info:
        read_json(b'"\xfd"', origin="en.json")
    assert info.value.path == "en.json"
    assert info.value.pointer == ""
    assert "UTF-8" in str(info.value)


def test_read_json_reports_line_and_column() -> None:
    with pytest.raises(InvalidCatalogError) as info:
        read_json(b'{\n  "a": "b",\n}', origin="tr.json")
    message = str(info.value)
    assert message.startswith("tr.json: line ")
    assert "column" in message
    assert info.value.pointer == ""


def test_read_json_accepts_one_bom_and_turkish_text() -> None:
    raw = '﻿{"city": "İstanbul ılık"}'.encode()
    assert read_json(raw, origin="tr.json") == {"city": "İstanbul ılık"}


def test_escape_pointer_token() -> None:
    assert escape_pointer_token("c/d~e") == "c~1d~0e"


# --- formatting -------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "{0}",  # positional field
        "{a.b}",  # attribute field
        "{a[0]}",  # index field
        "{}",  # empty name
        "{x!r}",  # conversion
        "{x:>10}",  # format spec
        "{name",  # unbalanced brace
        "a}b",  # stray closing brace
        "{İsim}",  # non-ASCII name
    ],
)
def test_compile_template_rejects(text: str) -> None:
    with pytest.raises(TemplateError, match=r"\{\{"):
        compile_template(text)


def test_compile_template_segments() -> None:
    template = compile_template("{{lit}} {n} and {n}")
    assert template.segments == ("{lit} ", "n", " and ", "n", "")
    assert template.fields == frozenset({"n"})
    assert template.source == "{{lit}} {n} and {n}"


def test_render_keeps_missing_placeholder_literal() -> None:
    assert compile_template("Hi {name}, {other}").render({"name": "Enes"}) == (
        "Hi Enes, {other}"
    )


def test_render_never_reinterpolates_values() -> None:
    template = compile_template("{a}{a}{b}")
    assert template.render({"a": "{name}"}) == "{name}{name}{b}"


def test_render_plain_text_and_str_conversion() -> None:
    assert compile_template("plain").render({}) == "plain"
    assert compile_template("{n} items").render({"n": 3}) == "3 items"


def test_template_is_immutable_value() -> None:
    template = compile_template("Hi {name}")
    with pytest.raises(AttributeError, match="immutable"):
        template._source = "x"
    assert repr(template) == "Template('Hi {name}')"
    assert template == compile_template("Hi {name}")
    assert hash(template) == hash(compile_template("Hi {name}"))
    assert template != "Hi {name}"


# --- locale -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "canonical"),
    [
        ("pt_BR", "pt-BR"),
        ("zh-hant-tw", "zh-Hant-TW"),
        ("EN", "en"),
        ("TR", "tr"),
        ("es-419", "es-419"),
    ],
)
def test_normalize(raw: str, canonical: str) -> None:
    assert normalize(raw) == canonical


@pytest.mark.parametrize("raw", [42, None, "İt", "tr-İ", "", "english", "x" * 129])
def test_normalize_rejects(raw: Any) -> None:
    with pytest.raises(InvalidLocaleError) as info:
        normalize(raw)
    assert info.value.tag == raw


def test_fallback_chain_deduplicates_in_order() -> None:
    chain = fallback_chain("pt-BR", {"pt-BR": ("pt", "en", "pt")}, "en")
    assert chain == ("pt-BR", "pt", "en")
    assert fallback_chain("en", {}, "en") == ("en",)


# --- loaders: base and filesystem -------------------------------------------


def test_raw_source_is_immutable() -> None:
    source = RawSource({"a": "b"}, "en.json")
    assert (source.data, source.origin, source.namespace) == (
        {"a": "b"},
        "en.json",
        None,
    )
    assert repr(source) == "RawSource(origin='en.json', namespace=None)"
    with pytest.raises(AttributeError):
        source._origin = "x"


def test_filesystem_loader_rejects_non_locale_file(
    make_locales_dir: MakeLocalesDir,
) -> None:
    root = make_locales_dir({"en": {}, "common": {}})
    with pytest.raises(InvalidCatalogError) as info:
        FilesystemLoader(root).discover_locales()
    assert info.value.path == "common.json"


def test_filesystem_loader_ignores_dotfiles_other_files_and_dirs(
    make_locales_dir: MakeLocalesDir,
) -> None:
    root = make_locales_dir({"en": {"a": "b"}})
    (root / ".hidden.json").write_text("{", encoding="utf-8")
    (root / "notes.txt").write_text("notes", encoding="utf-8")
    (root / ".git").mkdir()
    loader = FilesystemLoader(root)
    assert loader.discover_locales() == frozenset({"en"})
    assert loader.root == root
    assert repr(loader) == f"FilesystemLoader({str(root)!r})"
    (source,) = loader.load("en")
    assert (source.origin, source.data) == ("en.json", {"a": "b"})


def test_filesystem_loader_rejects_colliding_files(tmp_path: Path) -> None:
    (tmp_path / "pt_BR.json").write_text("{}", encoding="utf-8")
    (tmp_path / "pt-BR.json").write_text("{}", encoding="utf-8")
    with pytest.raises(InvalidCatalogError) as info:
        FilesystemLoader(tmp_path).discover_locales()
    assert (info.value.path, info.value.other_path) == ("pt_BR.json", "pt-BR.json")


def test_filesystem_loader_needs_existing_directory(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationError):
        FilesystemLoader(tmp_path / "missing").discover_locales()


def test_filesystem_loader_only_loads_discovered_tags(
    make_locales_dir: MakeLocalesDir,
) -> None:
    loader = FilesystemLoader(make_locales_dir())
    with pytest.raises(LocJsonError, match="not discovered"):
        loader.load("en")
    loader.discover_locales()
    with pytest.raises(LocJsonError, match="not discovered"):
        loader.load("../en")


# --- loaders: memory --------------------------------------------------------


def test_dict_loader_serves_normalized_tags() -> None:
    data = {"en": {"a": "b"}}
    loader = DictLoader({"pt_BR": {}, **data})
    assert loader.discover_locales() == frozenset({"en", "pt-BR"})
    (source,) = loader.load("en")
    assert source.data is data["en"]
    assert source.origin == "<dict>/en"
    assert repr(loader) == "DictLoader(locales=['en', 'pt-BR'])"
    assert isinstance(loader, Loader)
    with pytest.raises(LocJsonError, match="not held"):
        loader.load("tr")


def test_dict_loader_rejects_invalid_key() -> None:
    with pytest.raises(InvalidCatalogError) as info:
        DictLoader({"english": {}})
    assert info.value.path == "<dict>/english"
    bad: Any = {1: {}}
    with pytest.raises(InvalidCatalogError) as info:
        DictLoader(bad)
    assert info.value.path == "<dict>/1"


def test_dict_loader_rejects_colliding_keys() -> None:
    with pytest.raises(InvalidCatalogError) as info:
        DictLoader({"pt_BR": {}, "pt-BR": {}})
    assert (info.value.path, info.value.other_path) == ("<dict>/pt-BR", "<dict>/pt_BR")
    assert info.value.locale == "pt-BR"


# --- catalog ----------------------------------------------------------------


def _build(
    data: object, origin: str = "en.json", namespace: str | None = None
) -> BuildResult:
    return build_catalog("en", [RawSource(data, origin, namespace)])


def test_non_string_leaf_is_an_issue_with_pointer() -> None:
    result = _build({"count": 3, "flag": True})
    assert result.catalog is None
    assert [(i.path, i.pointer, i.locale) for i in result.issues] == [
        ("en.json", "/count", "en"),
        ("en.json", "/flag", "en"),
    ]
    assert "got int" in result.issues[0].problem
    assert "got bool" in result.issues[1].problem
    with pytest.raises(InvalidCatalogError) as info:
        result.unwrap()
    assert (info.value.path, info.value.pointer) == ("en.json", "/count")
    assert str(info.value).endswith("(and 1 more)")


def test_null_empty_and_dollar_keys_are_skipped() -> None:
    catalog = _build(
        {"a": None, "b": "", "c": "C", "$meta": {"direction": "rtl"}}
    ).unwrap()
    assert dict(catalog) == {"c": compile_template("C")}


def test_namespace_prefix() -> None:
    catalog = _build({"greeting": "Hi"}, "en/common.json", "common").unwrap()
    assert list(catalog) == ["common.greeting"]


def test_top_level_must_be_an_object() -> None:
    (issue,) = _build(["a"]).issues
    assert issue.pointer == ""
    assert "got list" in issue.problem


def test_template_errors_and_keys_get_escaped_pointers() -> None:
    bad_keys: Any = {"a/b": {"c~d": "{x!r}"}, 1: "one"}
    issues = _build(bad_keys).issues
    assert [i.pointer for i in issues] == ["/1", "/a~1b/c~0d"]
    assert "object keys must be strings" in issues[0].problem
    assert "conversion" in issues[1].problem


def test_catalog_is_an_immutable_mapping() -> None:
    template = compile_template("Home")
    catalog = Catalog("en", {"nav.home": template}, Meta("en", "ltr"))
    assert catalog["nav.home"] is template
    assert catalog.get("nav.home") is template
    assert catalog.get("missing") is None
    assert catalog.get("missing", template) is template
    assert "nav.home" in catalog
    assert "missing" not in catalog
    assert len(catalog) == 1
    assert (catalog.locale, catalog.direction, catalog.meta.locale) == (
        "en",
        "ltr",
        "en",
    )
    assert repr(catalog) == "Catalog(locale='en', keys=1)"
    assert repr(catalog.meta) == "Meta(locale='en', direction='ltr')"
    assert Catalog("en", {}).direction is None
    with pytest.raises(AttributeError):
        catalog._locale = "tr"
    with pytest.raises(AttributeError):
        catalog.meta._direction = "rtl"


def test_build_result_unwrap_returns_catalog() -> None:
    result = _build({"a": "b"})
    assert result.issues == ()
    assert result.unwrap() is result.catalog
    catalog, issues = result
    assert catalog is result.catalog
    assert issues == ()


# --- localizer --------------------------------------------------------------


def test_localizer_needs_exactly_one_source(make_locales_dir: MakeLocalesDir) -> None:
    root = make_locales_dir()
    with pytest.raises(ConfigurationError):
        Localizer(root, loader=FilesystemLoader(root))
    with pytest.raises(ConfigurationError):
        Localizer()


def test_localizer_validates_configuration(sample_catalogs: Catalogs) -> None:
    loader = DictLoader(sample_catalogs)
    bad_policy: Any = "silent"
    with pytest.raises(ConfigurationError, match="missing="):
        Localizer(loader=loader, missing=bad_policy)
    with pytest.raises(ConfigurationError, match="not among the discovered"):
        Localizer(loader=loader, default_locale="de")
    with pytest.raises(InvalidLocaleError):
        Localizer(loader=loader, default_locale="english")
    with pytest.raises(InvalidLocaleError):
        Localizer(loader=loader, fallbacks={"pt-BR": ["portuguese"]})


def test_missing_key_returns_key(make_locales_dir: MakeLocalesDir) -> None:
    l10n = Localizer(make_locales_dir())
    assert l10n.t("nav.profile") == "nav.profile"
    assert l10n.t("nav") == "nav"


def test_fallbacks_serve_parent_text(make_locales_dir: MakeLocalesDir) -> None:
    root = make_locales_dir()
    l10n = Localizer(root, fallbacks={"pt_BR": ["pt"]})
    assert l10n.t("nav.home", locale="pt-BR") == "Início"
    assert l10n.t("nav.settings", locale="pt_BR") == "Configurações"
    assert l10n.t("only_en", locale="pt-BR") == "English only"
    single = Localizer(root, fallbacks={"pt-BR": ("pt",)})
    assert single.t("nav.home", locale="pt-BR") == "Início"
    # Script-aware truncation reaches pt without explicit fallbacks (LOC-03).
    assert Localizer(root).t("nav.home", locale="pt-BR") == "Início"
    assert Localizer(root).t("nav.home", locale="de-AT") == "Home"


def test_unknown_or_invalid_request_locale_uses_default(
    make_locales_dir: MakeLocalesDir,
) -> None:
    l10n = Localizer(make_locales_dir())
    assert l10n.t("nav.home", locale="de") == "Home"
    assert l10n.t("nav.home", locale="İt") == "Home"
    assert l10n.t("nav.home", locale="x" * 1000) == "Home"


def test_count_is_available_as_placeholder(make_locales_dir: MakeLocalesDir) -> None:
    l10n = Localizer(make_locales_dir())
    assert l10n.t("inbox.messages", count=3) == "You have 3 messages"
    assert l10n.t("greeting", name="{count}", count=2) == "Hello, {count}!"


def test_turkish_text_round_trips(make_locales_dir: MakeLocalesDir) -> None:
    l10n = Localizer(make_locales_dir(), default_locale="tr")
    assert l10n.t("city") == "İstanbul'da ılık bir akşam"
    assert l10n.t("inbox.messages", count=0) == "Hiç mesajınız yok"


def test_context_is_reserved(make_locales_dir: MakeLocalesDir) -> None:
    l10n = Localizer(make_locales_dir())
    reserved: Any = "formal"
    with pytest.raises(LocJsonError, match="reserved"):
        l10n.t("greeting", context=reserved)


def test_dict_loader_matches_filesystem(
    make_locales_dir: MakeLocalesDir, sample_catalogs: Catalogs
) -> None:
    from_disk = Localizer(make_locales_dir())
    from_dict = Localizer(loader=DictLoader(sample_catalogs))
    for locale in ("en", "tr"):
        assert from_dict.t("greeting", locale=locale, name="Enes") == from_disk.t(
            "greeting", locale=locale, name="Enes"
        )
    assert from_dict.locales == from_disk.locales
    assert from_dict.default_locale == "en"
    assert repr(from_dict).startswith("Localizer(loader=DictLoader(")


def test_invalid_leaf_raises_on_first_lookup(make_locales_dir: MakeLocalesDir) -> None:
    l10n = Localizer(make_locales_dir({"en": {"count": 3}}))
    with pytest.raises(InvalidCatalogError) as info:
        l10n.t("count")
    assert (info.value.path, info.value.pointer) == ("en.json", "/count")
    assert isinstance(info.value, ValueError)


def test_catalogs_load_once_per_requested_locale(sample_catalogs: Catalogs) -> None:
    class CountingLoader(DictLoader):
        def __init__(self, catalogs: Catalogs) -> None:
            super().__init__(catalogs)
            self.calls: list[str] = []

        @override
        def load(self, locale: str) -> tuple[RawSource, ...]:
            self.calls.append(locale)
            return super().load(locale)

    loader = CountingLoader(sample_catalogs)
    l10n = Localizer(loader=loader)
    for _ in range(3):
        assert l10n.t("greeting", locale="tr", name="Enes") == "Merhaba, Enes!"
        assert l10n.t("only_en", locale="tr") == "English only"
    assert sorted(loader.calls) == ["en", "tr"]


def test_empty_catalog_is_cached(sample_catalogs: Catalogs) -> None:
    sample_catalogs["de"] = {}
    calls: list[str] = []

    class Spy(DictLoader):
        @override
        def load(self, locale: str) -> tuple[RawSource, ...]:
            calls.append(locale)
            return super().load(locale)

    l10n = Localizer(loader=Spy(sample_catalogs), default_locale="de")
    assert l10n.t("x") == "x"
    assert l10n.t("x") == "x"
    assert calls == ["de"]


def test_cold_load_rechecks_snapshot_under_lock(sample_catalogs: Catalogs) -> None:
    l10n = Localizer(loader=DictLoader(sample_catalogs))
    l10n._load("tr")
    first = l10n._snapshot.catalogs["tr"]
    # A second cold path (as a racing thread would take) reuses the published catalog.
    l10n._load("tr")
    assert l10n._snapshot.catalogs["tr"] is first
