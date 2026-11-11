"""Tests for the FastAPI example: the response follows Accept-Language."""

from __future__ import annotations

import pytest
from app import app
from fastapi.testclient import TestClient

client = TestClient(app)


@pytest.mark.parametrize(
    ("header", "locale", "title"),
    [
        ("tr-TR,tr;q=0.9,en;q=0.8", "tr", "Fırınımıza hoş geldiniz"),
        ("de-DE,de;q=0.9,en;q=0.5", "en", "Welcome to the bakery"),
        ("fr", "en", "Welcome to the bakery"),  # no French catalog
        ("", "en", "Welcome to the bakery"),
    ],
)
def test_home_follows_accept_language(header: str, locale: str, title: str) -> None:
    response = client.get("/", headers={"Accept-Language": header})
    assert response.status_code == 200
    assert response.json()["locale"] == locale
    assert response.json()["title"] == title
    assert response.headers["Content-Language"] == locale


def test_no_header_means_default_locale() -> None:
    response = client.get("/")
    assert response.json()["greeting"] == "Hello, Ada!"


def test_cart_plurals() -> None:
    tr = {"Accept-Language": "tr"}
    assert client.get("/cart", params={"items": 0}).json() == {
        "summary": "Your basket is empty"
    }
    assert client.get("/cart", params={"items": 1}).json() == {
        "summary": "1 loaf in your basket"
    }
    assert client.get("/cart", params={"items": 3}, headers=tr).json() == {
        "summary": "Sepetinizde 3 somun var"
    }


def test_locale_does_not_leak_between_requests() -> None:
    assert client.get("/", headers={"Accept-Language": "tr"}).json()["locale"] == "tr"
    assert client.get("/").json()["locale"] == "en"
