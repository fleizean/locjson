"""Shared fixtures: the PROJECT.md sample catalogs in both directory layouts."""

from __future__ import annotations

import copy
import itertools
import json
from typing import TYPE_CHECKING, Literal, Protocol

import pytest

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

Catalogs = dict[str, dict[str, object]]

_SAMPLE: Catalogs = {
    "en": {
        "greeting": "Hello, {name}!",
        "nav": {"home": "Home", "settings": "Settings"},
        "inbox": {
            "messages": {
                "zero": "You have no messages",
                "one": "You have {count} message",
                "other": "You have {count} messages",
            }
        },
        "braces": "Use {{name}} to write {name}",
        "only_en": "English only",
    },
    "tr": {
        "greeting": "Merhaba, {name}!",
        "nav": {"home": "Ana Sayfa", "settings": "Ayarlar"},
        "inbox": {
            "messages": {
                "zero": "Hiç mesajınız yok",
                "one": "{count} mesajınız var",
                "other": "{count} mesajınız var",
            }
        },
        "city": "İstanbul'da ılık bir akşam",
    },
    "pt": {"nav": {"home": "Início", "settings": "Definições"}},
    "pt-BR": {"nav": {"settings": "Configurações"}},
    "zh": {"nav": {"home": "首页", "settings": "设置"}},
    "zh-Hant": {"nav": {"home": "首頁"}},
    "ar": {"$meta": {"direction": "rtl"}, "nav": {"home": "الرئيسية"}},
}


class MakeLocalesDir(Protocol):
    def __call__(
        self,
        catalogs: Mapping[str, object] | None = None,
        *,
        layout: Literal["single", "namespaced"] = "single",
        namespace: str = "common",
    ) -> Path: ...


@pytest.fixture
def sample_catalogs() -> Catalogs:
    """A fresh deep copy of the sample catalogs for every call."""
    return copy.deepcopy(_SAMPLE)


@pytest.fixture
def make_locales_dir(tmp_path: Path) -> MakeLocalesDir:
    """Write catalogs to a fresh directory and return its path."""
    counter = itertools.count()

    def factory(
        catalogs: Mapping[str, object] | None = None,
        *,
        layout: Literal["single", "namespaced"] = "single",
        namespace: str = "common",
    ) -> Path:
        root = tmp_path / f"locales{next(counter)}"
        root.mkdir()
        for tag, data in (_SAMPLE if catalogs is None else catalogs).items():
            if layout == "namespaced":
                (root / tag).mkdir()
                target = root / tag / f"{namespace}.json"
            else:
                target = root / f"{tag}.json"
            text = json.dumps(data, ensure_ascii=False, indent=2)
            target.write_text(text, encoding="utf-8")
        return root

    return factory
