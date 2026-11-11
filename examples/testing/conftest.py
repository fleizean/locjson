"""Fixtures: a strict Localizer over in-memory catalogs, and one over the real files."""

from __future__ import annotations

import pytest
import shop

from locjson import DictLoader, Localizer

# Test catalogs live next to the tests, so the expected strings are obvious.
CATALOGS = {
    "en": {
        "order": {
            "thanks": "Thanks, {name}!",
            "items": {
                "zero": "No items.",
                "one": "{count} item.",
                "other": "{count} items.",
            },
            "total": "Total: {amount}",
        }
    },
    "tr": {
        "order": {
            "thanks": "Teşekkürler, {name}!",
            "items": {
                "zero": "Ürün yok.",
                "one": "{count} ürün.",
                "other": "{count} ürün.",
            },
            "total": "Toplam: {amount}",
        }
    },
}


@pytest.fixture(autouse=True)
def _no_strict_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make every test independent of a LOCJSON_STRICT set in the shell."""
    monkeypatch.delenv("LOCJSON_STRICT", raising=False)


@pytest.fixture
def l10n() -> Localizer:
    """A strict Localizer over CATALOGS: any slip raises instead of passing."""
    return Localizer(loader=DictLoader(CATALOGS), strict=True)


@pytest.fixture
def real_l10n() -> Localizer:
    """The application's own catalogs, strict."""
    return shop.make_localizer(strict=True)
