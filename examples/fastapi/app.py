"""A FastAPI app that answers in the language of the Accept-Language header.

Run it with ``uvicorn app:app --reload``, then try
``curl -H "Accept-Language: tr" http://127.0.0.1:8000/``.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import FastAPI, Request, Response

from locjson import Localizer

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

l10n = Localizer(Path(__file__).resolve().parent / "locales")
app = FastAPI()


@app.middleware("http")
async def locale_from_header(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Use the best locale for the request while the endpoint runs."""
    header = request.headers.get("accept-language")
    # use() sets the current locale for this request only: each request runs
    # in its own context, and the previous locale comes back on exit.
    with l10n.use(l10n.negotiate(header)) as locale:
        response = await call_next(request)
    response.headers["Content-Language"] = locale
    return response


@app.get("/")
async def home() -> dict[str, str]:
    """Return the home page texts in the request's language."""
    return {
        "locale": l10n.current_locale,
        "title": l10n.t("home.title"),
        "greeting": l10n.t("home.greeting", name="Ada"),
    }


@app.get("/cart")
async def cart(items: int = 0) -> dict[str, str]:
    """Return a pluralized basket summary, e.g. ``/cart?items=3``."""
    return {"summary": l10n.t("cart.items", count=items)}
