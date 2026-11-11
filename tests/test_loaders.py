"""FilesystemLoader layouts and discovery rules, DictLoader rules (CAT-01, CAT-09)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from locjson import FilesystemLoader, Localizer

if TYPE_CHECKING:
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
