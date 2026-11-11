"""Shared fixtures: the sample catalogs in both layouts, and a filesystem audit."""

from __future__ import annotations

import contextlib
import copy
import itertools
import json
import sys
from typing import TYPE_CHECKING, Literal, Protocol

import pytest

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping
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


_AUDITED_EVENTS = frozenset({"open", "os.scandir", "os.listdir"})


class IoAudit:
    """Records filesystem audit events while :meth:`watching` is active.

    Audit hooks can never be removed once added, so one hook is registered for
    the whole test session, at conftest import, and it only records while the
    ``armed`` flag is set. ``open`` covers ``open()`` and ``Path.read_bytes``;
    ``os.scandir`` and ``os.listdir`` cover directory listings (``is_file()``
    and ``stat`` raise no audit event).
    """

    def __init__(self) -> None:
        self.armed = False
        self.events: list[tuple[str, str]] = []

    def hook(self, event: str, args: tuple[object, ...]) -> None:
        if self.armed and event in _AUDITED_EVENTS:
            self.events.append((event, str(args[0])[:200] if args else ""))

    @contextlib.contextmanager
    def watching(self) -> Iterator[IoAudit]:
        """Clear the recorded events and record until the block exits."""
        self.events.clear()
        self.armed = True
        try:
            yield self
        finally:
            self.armed = False


_IO_AUDIT = IoAudit()
sys.addaudithook(_IO_AUDIT.hook)


@pytest.fixture
def io_audit() -> IoAudit:
    """The session-wide filesystem audit, disarmed."""
    _IO_AUDIT.armed = False
    return _IO_AUDIT


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
