"""A small piece of application code that renders translated messages.

The function takes the Localizer as an argument instead of importing a global
one, so tests can pass a Localizer built from in-memory catalogs.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from locjson import Localizer

LOCALES = Path(__file__).resolve().parent / "locales"

# Every key this module uses. The tests check that each locale has them all.
KEYS = ("order.thanks", "order.items", "order.total")


def make_localizer(*, strict: bool | None = None) -> Localizer:
    """Build the application's Localizer from ``locales/``."""
    return Localizer(LOCALES, strict=strict)


def order_confirmation(
    l10n: Localizer, locale: str, *, name: str, items: int, total: Decimal
) -> str:
    """Render the confirmation line shown after checkout."""
    t = l10n.for_locale(locale).scope("order")
    return " ".join(
        [
            t("thanks", name=name),
            t("items", count=items),
            # Format numbers in Python; placeholders take no format specs.
            t("total", amount=f"{total:.2f}"),
        ]
    )


if __name__ == "__main__":
    app_l10n = make_localizer()
    for locale in ("en", "tr"):
        print(
            order_confirmation(app_l10n, locale, name="Ada", items=2, total=Decimal(42))
        )
