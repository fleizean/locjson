"""A single-file Django project that answers in the Accept-Language language.

Run it with ``python app.py runserver``, then try
``curl -H "Accept-Language: tr" http://127.0.0.1:8000/``.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from django.conf import settings
from django.http import JsonResponse
from django.urls import path

from locjson import Localizer

if TYPE_CHECKING:
    from collections.abc import Callable

    from django.http import HttpRequest, HttpResponse

settings.configure(
    DEBUG=os.environ.get("DJANGO_DEBUG", "1") == "1",
    # A development-only key. Read a real one from the environment in production.
    SECRET_KEY=os.environ.get("DJANGO_SECRET_KEY", "locjson-example-insecure-key"),
    ALLOWED_HOSTS=["localhost", "127.0.0.1", "testserver"],
    ROOT_URLCONF=__name__,
    MIDDLEWARE=[f"{__name__}.locale_middleware"],
)

l10n = Localizer(Path(__file__).resolve().parent / "locales")


def locale_middleware(
    get_response: Callable[[HttpRequest], HttpResponse],
) -> Callable[[HttpRequest], HttpResponse]:
    """Use the best locale for each request while its view runs."""

    def middleware(request: HttpRequest) -> HttpResponse:
        header = request.headers.get("Accept-Language")
        # use() restores the previous locale when the block ends, so nothing
        # stays behind on the worker thread for the next request.
        with l10n.use(l10n.negotiate(header)) as locale:
            response = get_response(request)
        response.headers["Content-Language"] = locale
        return response

    return middleware


def json_response(data: dict[str, str]) -> JsonResponse:
    """Return ``data`` as UTF-8 JSON, keeping non-ASCII text readable."""
    return JsonResponse(data, json_dumps_params={"ensure_ascii": False})


def home(_request: HttpRequest) -> JsonResponse:
    """Return the home page texts in the request's language."""
    return json_response(
        {
            "locale": l10n.current_locale,
            "title": l10n.t("home.title"),
            "greeting": l10n.t("home.greeting", name="Ada"),
        }
    )


def cart(request: HttpRequest) -> JsonResponse:
    """Return a pluralized basket summary, e.g. ``/cart?items=3``."""
    items = int(request.GET.get("items", "0"))
    return json_response({"summary": l10n.t("cart.items", count=items)})


urlpatterns = [
    path("", home),
    path("cart", cart),
]


if __name__ == "__main__":
    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)
