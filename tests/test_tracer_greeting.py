"""Tracer: a JSON file on disk reaches ``Localizer.t`` through every layer."""

from __future__ import annotations

from typing import TYPE_CHECKING

from locjson import Localizer

if TYPE_CHECKING:
    from tests.conftest import MakeLocalesDir


def test_greeting_renders_from_json_files(make_locales_dir: MakeLocalesDir) -> None:
    l10n = Localizer(path=make_locales_dir(), default_locale="en")

    assert l10n.t("greeting", name="Enes") == "Hello, Enes!"
    assert l10n.t("greeting", locale="tr", name="Enes") == "Merhaba, Enes!"
    assert l10n.t("nav.home") == "Home"
    assert l10n.t("braces", name="Enes") == "Use {name} to write Enes"
    assert {"en", "zh-Hant"} <= l10n.locales
