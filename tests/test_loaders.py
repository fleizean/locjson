"""FilesystemLoader layouts and discovery rules, DictLoader rules (CAT-01, CAT-09)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Literal

import pytest

from locjson import (
    ConfigurationError,
    DictLoader,
    FilesystemLoader,
    InvalidCatalogError,
    Localizer,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from tests.conftest import MakeLocalesDir


def _write(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


# --- layouts ----------------------------------------------------------------


def test_namespaced_layout_prefixes_keys(make_locales_dir: MakeLocalesDir) -> None:
    l10n = Localizer(path=make_locales_dir(layout="namespaced"))
    assert l10n.t("common.greeting", locale="tr", name="Enes") == "Merhaba, Enes!"
    assert l10n.t("common.nav.home") == "Home"
    assert l10n.t("common.city", locale="tr") == "İstanbul'da ılık bir akşam"
    assert l10n.t("greeting", name="Enes") == "greeting"


def test_single_layout_keeps_working(make_locales_dir: MakeLocalesDir) -> None:
    l10n = Localizer(path=make_locales_dir())
    assert l10n.t("greeting", locale="tr", name="Enes") == "Merhaba, Enes!"
    assert l10n.t("nav.home") == "Home"


def test_several_namespace_files_in_one_locale(tmp_path: Path) -> None:
    _write(tmp_path / "en" / "common.json", {"greeting": "Hello, {name}!"})
    _write(tmp_path / "en" / "nav.json", {"home": "Home"})
    loader = FilesystemLoader(tmp_path)
    assert loader.discover_locales() == frozenset({"en"})
    sources = loader.load("en")
    assert [(s.origin, s.namespace) for s in sources] == [
        ("en/common.json", "common"),
        ("en/nav.json", "nav"),
    ]
    l10n = Localizer(loader=loader)
    assert l10n.t("common.greeting", name="Enes") == "Hello, Enes!"
    assert l10n.t("nav.home") == "Home"


def test_layouts_can_differ_per_locale(tmp_path: Path) -> None:
    _write(tmp_path / "en.json", {"common": {"greeting": "Hello, {name}!"}})
    _write(tmp_path / "tr" / "common.json", {"greeting": "Merhaba, {name}!"})
    l10n = Localizer(path=tmp_path)
    assert l10n.locales == frozenset({"en", "tr"})
    assert l10n.t("common.greeting", locale="tr", name="Enes") == "Merhaba, Enes!"
    assert l10n.t("common.greeting", name="Enes") == "Hello, Enes!"


# --- discovery: ignored entries ---------------------------------------------


def test_discovery_ignores_dot_entries_and_non_json_files(tmp_path: Path) -> None:
    _write(tmp_path / "en.json", {"a": "b"})
    (tmp_path / ".hidden.json").write_text("{", encoding="utf-8")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "HEAD").write_text("ref", encoding="utf-8")
    (tmp_path / "README.md").write_text("# locales", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("notes", encoding="utf-8")
    # The suffix match is exact and case-sensitive. "tr" rather than "en", so
    # the names cannot clash on a case-insensitive filesystem (Pitfall 11).
    (tmp_path / "tr.JSON").write_text("{", encoding="utf-8")
    assert FilesystemLoader(tmp_path).discover_locales() == frozenset({"en"})


def test_namespace_scan_ignores_dot_entries_and_non_json_files(
    tmp_path: Path,
) -> None:
    _write(tmp_path / "en" / "common.json", {"a": "b"})
    (tmp_path / "en" / ".common.json").write_text("{", encoding="utf-8")
    (tmp_path / "en" / ".cache").mkdir()
    (tmp_path / "en" / "README.md").write_text("# en", encoding="utf-8")
    loader = FilesystemLoader(tmp_path)
    loader.discover_locales()
    assert [s.origin for s in loader.load("en")] == ["en/common.json"]


# --- discovery: strict naming and collisions --------------------------------


def _files(*names: str) -> Callable[[Path], None]:
    def build(root: Path) -> None:
        for name in names:
            if name.endswith("/"):
                (root / name).mkdir(parents=True)
            else:
                _write(root / name, {})

    return build


@pytest.mark.parametrize(
    ("names", "path", "other_path", "problem"),
    [
        pytest.param(
            ("en.json", "common.json"),
            "common.json",
            None,
            "'common.json' is not named after a valid locale tag",
            id="invalid-file-name",
        ),
        pytest.param(
            ("en.json", "root/"),
            "root/",
            None,
            "'root/' is not named after a valid locale tag",
            id="invalid-dir-name",
        ),
        pytest.param(
            ("en.json", "tr.json/"),
            "tr.json/",
            None,
            "'tr.json/' is not named after a valid locale tag",
            id="dir-named-like-a-file",
        ),
        pytest.param(
            ("en.UTF-8.json",),
            "en.UTF-8.json",
            None,
            "'en.UTF-8.json' is not named after a valid locale tag",
            id="posix-codeset-in-name",
        ),
        pytest.param(
            ("en.json", "en/"),
            "en.json",
            "en/",
            "locale 'en' is present in both layouts",
            id="both-layouts",
        ),
        pytest.param(
            ("pt_BR.json", "pt-BR.json"),
            "pt_BR.json",
            "pt-BR.json",
            "'pt_BR.json' and 'pt-BR.json' are the same locale 'pt-BR'",
            id="same-locale-files",
        ),
        pytest.param(
            ("pt_BR/", "pt-BR/"),
            "pt_BR/",
            "pt-BR/",
            "'pt_BR/' and 'pt-BR/' are the same locale 'pt-BR'",
            id="same-locale-dirs",
        ),
        pytest.param(
            ("pt_BR/", "pt-BR.json"),
            "pt_BR/",
            "pt-BR.json",
            "locale 'pt-BR' is present in both layouts",
            id="both-layouts-different-spelling",
        ),
    ],
)
def test_discovery_rejects(
    tmp_path: Path,
    names: tuple[str, ...],
    path: str,
    other_path: str | None,
    problem: str,
) -> None:
    _files(*names)(tmp_path)
    with pytest.raises(InvalidCatalogError) as info:
        FilesystemLoader(tmp_path).discover_locales()
    assert (info.value.path, info.value.other_path) == (path, other_path)
    assert info.value.problem == problem


def test_both_layouts_error_names_both_entries_through_localizer(
    tmp_path: Path,
) -> None:
    _files("en.json", "en/common.json")(tmp_path)
    with pytest.raises(InvalidCatalogError) as info:
        Localizer(path=tmp_path)
    assert (info.value.path, info.value.other_path) == ("en.json", "en/")
    assert info.value.locale == "en"
    assert str(info.value) == (
        "en.json: locale 'en' is present in both layouts (conflicts with en/)"
    )


@pytest.mark.parametrize(
    ("name", "path", "problem"),
    [
        pytest.param(
            "en/sub/",
            "en/sub/",
            "namespaces are one level deep; 'en/sub/' is a directory",
            id="subdirectory",
        ),
        pytest.param(
            "en/a.b.json",
            "en/a.b.json",
            "namespace 'a.b' must not contain '.' or start with '$'",
            id="dot-in-stem",
        ),
        pytest.param(
            "en/$x.json",
            "en/$x.json",
            "namespace '$x' must not contain '.' or start with '$'",
            id="dollar-stem",
        ),
    ],
)
def test_namespace_rules(tmp_path: Path, name: str, path: str, problem: str) -> None:
    _files("en/common.json", name)(tmp_path)
    loader = FilesystemLoader(tmp_path)
    assert loader.discover_locales() == frozenset({"en"})
    with pytest.raises(InvalidCatalogError) as info:
        loader.load("en")
    assert (info.value.path, info.value.problem) == (path, problem)
    assert info.value.locale == "en"


def test_namespace_rules_surface_on_first_lookup(tmp_path: Path) -> None:
    _files("en/common.json", "en/sub/")(tmp_path)
    l10n = Localizer(path=tmp_path)
    with pytest.raises(InvalidCatalogError, match="one level deep"):
        l10n.t("common.greeting")


def test_locale_dir_without_namespaces_is_an_empty_catalog(tmp_path: Path) -> None:
    (tmp_path / "en").mkdir()
    (tmp_path / "en" / "notes.txt").write_text("notes", encoding="utf-8")
    loader = FilesystemLoader(tmp_path)
    assert loader.discover_locales() == frozenset({"en"})
    assert loader.load("en") == ()
    assert Localizer(loader=loader).t("common.greeting") == "common.greeting"


# --- catalog root -----------------------------------------------------------


def test_missing_root_is_a_configuration_error(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationError, match="does not exist"):
        Localizer(path=tmp_path / "missing")


def test_file_root_is_a_configuration_error(tmp_path: Path) -> None:
    target = tmp_path / "en.json"
    _write(target, {})
    with pytest.raises(ConfigurationError, match="not a directory"):
        Localizer(path=target)


# --- idempotency and re-discovery -------------------------------------------


@pytest.mark.parametrize("layout", ["single", "namespaced"])
def test_discovery_and_load_are_idempotent(
    make_locales_dir: MakeLocalesDir, layout: Literal["single", "namespaced"]
) -> None:
    loader = FilesystemLoader(make_locales_dir(layout=layout))
    assert loader.discover_locales() == loader.discover_locales()
    first, second = loader.load("en"), loader.load("en")
    assert [(s.origin, s.namespace) for s in first] == [
        (s.origin, s.namespace) for s in second
    ]
    assert [s.data for s in first] == [s.data for s in second]


def test_rediscovery_replaces_the_previous_map(tmp_path: Path) -> None:
    _files("en.json")(tmp_path)
    loader = FilesystemLoader(tmp_path)
    assert loader.discover_locales() == frozenset({"en"})
    (tmp_path / "en.json").unlink()
    _files("en/common.json", "tr.json")(tmp_path)
    assert loader.discover_locales() == frozenset({"en", "tr"})
    assert [s.origin for s in loader.load("en")] == ["en/common.json"]


# --- DictLoader -------------------------------------------------------------


def test_dict_loader_collision_names_both_keys() -> None:
    with pytest.raises(InvalidCatalogError) as info:
        DictLoader({"pt_BR": {}, "pt-BR": {}})
    assert {info.value.path, info.value.other_path} == {"<dict>/pt_BR", "<dict>/pt-BR"}
    assert info.value.locale == "pt-BR"


def test_dict_loader_rejects_a_key_that_is_not_a_tag() -> None:
    with pytest.raises(InvalidCatalogError) as info:
        DictLoader({"not a tag": {}})
    assert info.value.path == "<dict>/not a tag"


def test_dict_loader_normalizes_keys() -> None:
    loader = DictLoader({"en_us": {"a": "b"}})
    assert loader.discover_locales() == frozenset({"en-US"})
    (source,) = loader.load("en-US")
    assert (source.origin, source.namespace) == ("<dict>/en-US", None)
