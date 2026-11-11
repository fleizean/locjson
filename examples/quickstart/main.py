"""A tour of the locjson basics, using the catalogs in ``locales/``.

Run it with ``python main.py``.
"""

from __future__ import annotations

from pathlib import Path

import locjson
from locjson import Localizer

LOCALES = Path(__file__).resolve().parent / "locales"


def section(title: str) -> None:
    """Print a section heading."""
    print(f"\n== {title}")


def main() -> None:
    """Translate a few messages in English and Turkish."""
    # The catalog folder is the first argument; default_locale is "en".
    l10n = Localizer(LOCALES)
    print("Locales:", ", ".join(sorted(l10n.locales)))

    section("Variables")
    print(l10n.t("greeting", name="Ada"))
    print(l10n.t("greeting", locale="tr", name="Ada"))
    print(l10n.t("help"))  # {{ and }} are literal braces

    section("Plurals")
    for count in (0, 1, 3):
        print(l10n.t("shelf.books", count=count))
    for count in (0, 1, 3):
        print(l10n.t("shelf.books", locale="tr", count=count))

    section("Fallback")
    # tr.json has no "farewell", so the lookup falls back to English.
    print(l10n.t("farewell", locale="tr", name="Ada"))
    # tr-TR has no catalog either: the chain is tr-TR -> tr -> en.
    print(l10n.t("app.name", locale="tr-TR"))
    # A key that exists nowhere returns the key itself (missing="key").
    print(l10n.t("shelf.title"))

    section("use(): the current locale")
    print("Current locale:", l10n.current_locale)
    with l10n.use("tr"):
        print("Current locale:", l10n.current_locale)
        print(l10n.t("app.name"))
        print(l10n.t("shelf.books", count=2))
    print("Current locale:", l10n.current_locale)

    section("for_locale(): a translator bound to one locale")
    t_tr = l10n.for_locale("tr")
    print(t_tr("greeting", name="Yağız"))
    print(t_tr("greeting", locale="en", name="Yağız"))  # an explicit locale wins

    section("Module-level API, for scripts and CLIs")
    locjson.setup(LOCALES)
    print(locjson.t("greeting", name="Enes"))
    with locjson.use("tr"):
        print(locjson.t("greeting", name="Enes"))


if __name__ == "__main__":
    main()
