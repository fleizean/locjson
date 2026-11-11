"""Send each user a daily digest e-mail in their own language.

There is no request here, so no "current locale" to rely on. Each job binds a
translator to its user's language with ``l10n.for_locale()``. A bound
translator never reads or changes shared state, so the jobs can run on a
thread pool (or as Celery/RQ tasks) side by side.

Nothing is sent: the e-mails are printed. Run it with ``python send_digests.py``.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from locjson import Localizer

LOCALES = Path(__file__).resolve().parent / "locales"

# One Localizer for the whole process. It is safe to share between threads.
l10n = Localizer(LOCALES)


@dataclass(frozen=True)
class User:
    """A user and the language stored in their profile."""

    name: str
    language: str
    unread: int


@dataclass(frozen=True)
class Email:
    """A rendered e-mail, ready for an SMTP client or an e-mail API."""

    to: str
    language: str
    subject: str
    body: str


USERS = [
    User("Ada", "en", 0),
    User("Yağız", "tr-TR", 3),  # no tr-TR catalog: tr-TR -> tr
    User("João", "pt_BR", 1),  # normalized to pt-BR, then pt-BR -> pt
    User("Hans", "de", 2),  # no German catalog: falls back to en
    User("Elif", "tr", 1),
    User("Sam", "not a locale!", 5),  # an invalid tag binds default_locale
]


def render_digest(user: User) -> Email:
    """Render one user's digest. Safe to call from any thread."""
    t = l10n.for_locale(user.language).scope("digest")
    body = "\n".join(
        [
            t("greeting", name=user.name),
            t("unread", count=user.unread),
            "",
            t("signoff"),
        ]
    )
    language = t.locale or l10n.default_locale
    return Email(user.name, language, t("subject", name=user.name), body)


def main() -> None:
    """Render every digest on a thread pool and print them in order."""
    with ThreadPoolExecutor(max_workers=4) as pool:
        emails = list(pool.map(render_digest, USERS))

    for email in emails:
        print(f"To: {email.to} [{email.language}]")
        print(f"Subject: {email.subject}")
        print(email.body)
        print("-" * 40)

    # The jobs never touched the current locale, and running them one by one
    # gives exactly the same e-mails.
    print("Current locale after the jobs:", l10n.current_locale)
    print("Same as a sequential run:", emails == [render_digest(u) for u in USERS])


if __name__ == "__main__":
    main()
