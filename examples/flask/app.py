"""A Flask app that answers in the language of the Accept-Language header.

Run it with ``flask --app app run``, then try
``curl -H "Accept-Language: tr" http://127.0.0.1:5000/``.
"""

from __future__ import annotations

from contextlib import ExitStack
from pathlib import Path

from flask import Flask, Response, g, request

from locjson import Localizer

l10n = Localizer(Path(__file__).resolve().parent / "locales")
app = Flask(__name__)
app.json.ensure_ascii = False  # keep Turkish text readable in JSON responses


@app.before_request
def enter_request_locale() -> None:
    """Make the best locale for this request the current locale."""
    header = request.headers.get("Accept-Language")
    # Enter l10n.use() here and leave it in teardown_request, so the previous
    # locale comes back even when the view raises. A plain set_locale() would
    # stay behind on the worker thread for the next request.
    stack = ExitStack()
    g.locale = stack.enter_context(l10n.use(l10n.negotiate(header)))
    g.locale_stack = stack


@app.after_request
def add_content_language(response: Response) -> Response:
    """Tell the client which language the response is in."""
    response.headers["Content-Language"] = g.get("locale", l10n.default_locale)
    return response


@app.teardown_request
def exit_request_locale(_error: BaseException | None) -> None:
    """Restore the locale that was current before the request."""
    stack: ExitStack | None = g.pop("locale_stack", None)
    if stack is not None:
        stack.close()


@app.get("/")
def home() -> dict[str, str]:
    """Return the home page texts in the request's language."""
    return {
        "locale": l10n.current_locale,
        "title": l10n.t("home.title"),
        "greeting": l10n.t("home.greeting", name="Ada"),
    }


@app.get("/cart")
def cart() -> dict[str, str]:
    """Return a pluralized basket summary, e.g. ``/cart?items=3``."""
    items = request.args.get("items", default=0, type=int)
    return {"summary": l10n.t("cart.items", count=items)}
