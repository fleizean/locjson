"""How to test code that uses locjson."""

from __future__ import annotations

import logging
from decimal import Decimal

import pytest
import shop

from locjson import (
    DictLoader,
    InterpolationError,
    Localizer,
    MissingTranslationError,
)

# --- Unit tests: in-memory catalogs, exact strings --------------------------


def test_confirmation_in_english(l10n: Localizer) -> None:
    text = shop.order_confirmation(l10n, "en", name="Ada", items=2, total=Decimal(5))
    assert text == "Thanks, Ada! 2 items. Total: 5.00"


def test_confirmation_in_turkish(l10n: Localizer) -> None:
    text = shop.order_confirmation(
        l10n, "tr", name="Yağız", items=1, total=Decimal("9.9")
    )
    assert text == "Teşekkürler, Yağız! 1 ürün. Toplam: 9.90"


@pytest.mark.parametrize(
    ("count", "expected"),
    [(0, "No items."), (1, "1 item."), (7, "7 items.")],
)
def test_plural_forms(l10n: Localizer, count: int, expected: str) -> None:
    assert l10n.t("order.items", count=count) == expected


# --- Strict mode turns slips into test failures ------------------------------


def test_a_typo_in_a_key_raises(l10n: Localizer) -> None:
    with pytest.raises(MissingTranslationError):
        l10n.t("order.thank", name="Ada")


def test_a_missing_variable_raises(l10n: Localizer) -> None:
    with pytest.raises(InterpolationError):
        l10n.t("order.thanks")  # forgot name=


def test_locjson_strict_turns_strict_mode_on(monkeypatch: pytest.MonkeyPatch) -> None:
    # The same switch works for a whole run: LOCJSON_STRICT=1 pytest
    monkeypatch.setenv("LOCJSON_STRICT", "1")
    assert shop.make_localizer().strict is True


def test_lenient_mode_logs_the_slip_once(caplog: pytest.LogCaptureFixture) -> None:
    # Without strict mode a slip renders something and logs a WARNING once.
    lenient = Localizer(loader=DictLoader({"en": {"hi": "Hi {name}"}}), strict=False)
    with caplog.at_level(logging.WARNING, logger="locjson"):
        assert lenient.t("hi") == "Hi {name}"
        assert lenient.t("hi") == "Hi {name}"
    assert len(caplog.records) == 1
    assert "name" in caplog.records[0].getMessage()


# --- Checks on the real catalog files ----------------------------------------


def test_catalogs_are_valid() -> None:
    # preload=True loads and validates every locale now, not at first use.
    Localizer(shop.LOCALES, preload=True)


@pytest.mark.parametrize("locale", ["en", "tr"])
@pytest.mark.parametrize("key", shop.KEYS)
def test_every_locale_has_every_key(locale: str, key: str) -> None:
    # With the locale under test as default_locale, its chain has no English
    # fallback that could hide a missing translation.
    only_this_locale = Localizer(shop.LOCALES, default_locale=locale)
    assert only_this_locale.has(key), f"{locale} is missing {key}"


def test_real_catalogs_render(real_l10n: Localizer) -> None:
    text = shop.order_confirmation(
        real_l10n, "tr", name="Ada", items=3, total=Decimal("12.5")
    )
    assert text == "Siparişiniz için teşekkürler, Ada! 3 ürün yola çıktı. Toplam: 12.50"
