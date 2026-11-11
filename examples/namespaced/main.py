"""Namespaced catalogs: one JSON file per feature, plus a right-to-left locale.

Each ``locales/<locale>/<namespace>.json`` file serves its keys under
``<namespace>.``: ``auth.json`` with ``login.title`` serves ``auth.login.title``.

Run it with ``python main.py``.
"""

from __future__ import annotations

from pathlib import Path

from locjson import Localizer

LOCALES = Path(__file__).resolve().parent / "locales"


def page_header(l10n: Localizer, locale: str) -> str:
    """Render a tiny HTML header with the right ``lang`` and ``dir``."""
    t = l10n.for_locale(locale)
    return (
        f'<html lang="{locale}" dir="{l10n.direction(locale)}">'
        f"<h1>{t('common.app.name')}</h1>"
    )


def main() -> None:
    """Show namespaced keys, scope() and text direction."""
    l10n = Localizer(LOCALES)
    print("Locales:", ", ".join(sorted(l10n.locales)))

    print("\n== Namespaced keys")
    print(l10n.t("common.greeting", name="Ada"))
    print(l10n.t("common.nav.trips", locale="tr"))
    print(l10n.t("auth.login.title", locale="ar"))

    print("\n== scope('auth'): no need to repeat the namespace")
    auth = l10n.scope("auth")
    for locale in ("en", "tr", "ar"):
        t = auth.for_locale(locale)
        print(f"{locale}: {t('login.title')} | {t('logout')}")
    print(auth.for_locale("tr")("login.failed", username="ada"))
    print(auth.for_locale("tr")("attempts_left", count=2))
    # ar/auth.json has no attempts_left yet, so English fills the gap.
    print(auth.for_locale("ar")("attempts_left", count=2))

    print("\n== direction(): from $meta, or a built-in table")
    for locale in ("en", "tr", "ar", "he"):
        print(f"{locale}: {l10n.direction(locale)}")

    print("\n== Putting it together")
    for locale in ("en", "ar"):
        print(page_header(l10n, locale))


if __name__ == "__main__":
    main()
