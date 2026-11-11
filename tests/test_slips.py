"""Translation slips: lenient by default, strict under ``missing="raise"`` (RT-04)."""

from __future__ import annotations

import json
import logging
import subprocess
import sys
from typing import TYPE_CHECKING, Any

import pytest

from locjson import (
    DictLoader,
    InterpolationError,
    Localizer,
    LocJsonError,
    MissingTranslationError,
)

if TYPE_CHECKING:
    from locjson.localizer import MissingPolicy
    from tests.conftest import Catalogs


def _l10n(catalogs: Catalogs, missing: MissingPolicy = "key") -> Localizer:
    return Localizer(loader=DictLoader(catalogs), missing=missing)


def _records(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [record for record in caplog.records if record.name == "locjson"]


# --- missing keys ------------------------------------------------------------


def test_missing_key_policies(sample_catalogs: Catalogs) -> None:
    assert _l10n(sample_catalogs).t("nope") == "nope"
    assert _l10n(sample_catalogs, "empty").t("nope") == ""
    with pytest.raises(MissingTranslationError) as info:
        _l10n(sample_catalogs, "raise").t("nope", locale="tr_TR")
    error = info.value
    assert isinstance(error, LookupError)
    assert isinstance(error, LocJsonError)
    assert not isinstance(error, KeyError)
    assert (error.key, error.locale) == ("nope", "tr-TR")


def test_callable_policy_gets_key_and_canonical_locale(
    sample_catalogs: Catalogs,
) -> None:
    calls: list[tuple[str, str]] = []

    def policy(key: str, locale: str) -> str:
        calls.append((key, locale))
        return f"[{key}]"

    l10n = _l10n(sample_catalogs, policy)
    assert l10n.t("nope", locale="pt_BR") == "[nope]"
    assert l10n.t("nope") == "[nope]"
    assert calls == [("nope", "pt-BR"), ("nope", "en")]


def test_empty_key_follows_the_policy(sample_catalogs: Catalogs) -> None:
    assert _l10n(sample_catalogs).t("") == ""
    assert _l10n(sample_catalogs, "empty").t("") == ""
    with pytest.raises(MissingTranslationError):
        _l10n(sample_catalogs, "raise").t("")


def test_found_keys_never_consult_the_policy(sample_catalogs: Catalogs) -> None:
    l10n = _l10n(sample_catalogs, "raise")
    assert l10n.t("greeting", name="Enes") == "Hello, Enes!"
    assert l10n.t("only_en", locale="tr") == "English only"


def test_each_missing_key_logs_one_debug_record(
    sample_catalogs: Catalogs, caplog: pytest.LogCaptureFixture
) -> None:
    l10n = _l10n(sample_catalogs)
    with caplog.at_level(logging.DEBUG, logger="locjson"):
        l10n.t("nope", locale="tr")
    records = _records(caplog)
    assert len(records) == 1
    assert records[0].levelno == logging.DEBUG
    message = records[0].getMessage()
    assert "'nope'" in message
    assert "'tr'" in message


def test_slips_log_nothing_at_warning_or_above(
    sample_catalogs: Catalogs, caplog: pytest.LogCaptureFixture
) -> None:
    l10n = _l10n(sample_catalogs)
    with caplog.at_level(logging.WARNING):
        l10n.t("nope")
        l10n.t("greeting")
        l10n.t("inbox.messages")
    assert _records(caplog) == []


# --- missing variables (INT-03) ------------------------------------------------


def test_missing_variable_keeps_the_placeholder(
    sample_catalogs: Catalogs, caplog: pytest.LogCaptureFixture
) -> None:
    l10n = _l10n(sample_catalogs)
    with caplog.at_level(logging.DEBUG, logger="locjson"):
        assert l10n.t("greeting") == "Hello, {name}!"
    records = _records(caplog)
    assert len(records) == 1
    assert "'name'" in records[0].getMessage()
    assert "'greeting'" in records[0].getMessage()


def test_missing_variable_raises_under_raise(sample_catalogs: Catalogs) -> None:
    l10n = _l10n(sample_catalogs, "raise")
    with pytest.raises(InterpolationError) as info:
        l10n.t("greeting")
    assert (info.value.name, info.value.key) == ("name", "greeting")
    assert isinstance(info.value, LocJsonError)
    assert not isinstance(info.value, KeyError)


def test_no_variables_at_all_is_lenient(sample_catalogs: Catalogs) -> None:
    assert _l10n(sample_catalogs).t("braces") == "Use {name} to write {name}"


def test_values_are_inserted_verbatim(sample_catalogs: Catalogs) -> None:
    l10n = _l10n(sample_catalogs)
    assert l10n.t("greeting", name="{name}") == "Hello, {name}!"
    assert l10n.t("greeting", name="Işık") == "Hello, Işık!"
    assert l10n.t("greeting", name="{count}", count=3) == "Hello, {count}!"


# --- missing count (PLUR-04) ---------------------------------------------------


def test_plural_without_count_uses_other(
    sample_catalogs: Catalogs, caplog: pytest.LogCaptureFixture
) -> None:
    l10n = _l10n(sample_catalogs)
    with caplog.at_level(logging.DEBUG, logger="locjson"):
        text = l10n.t("inbox.messages")
    assert text == "You have {count} messages"
    messages = [record.getMessage() for record in _records(caplog)]
    assert any("without count" in message for message in messages)


def test_plural_without_count_raises_under_raise(sample_catalogs: Catalogs) -> None:
    with pytest.raises(InterpolationError) as info:
        _l10n(sample_catalogs, "raise").t("inbox.messages")
    assert (info.value.key, info.value.name) == ("inbox.messages", "count")
    assert _l10n(sample_catalogs, "raise").t("inbox.messages", count=0) == (
        "You have no messages"
    )


# --- privacy (T-01-19) ---------------------------------------------------------


def test_records_never_carry_values_or_rendered_text(
    caplog: pytest.LogCaptureFixture,
) -> None:
    l10n = _l10n({"en": {"card": "{who} paid {amount}"}})
    with caplog.at_level(logging.DEBUG, logger="locjson"):
        text = l10n.t("card", who="SECRET-VALUE")
        l10n.t("nope", who="SECRET-VALUE")
    assert text == "SECRET-VALUE paid {amount}"
    records = _records(caplog)
    assert records
    for record in records:
        message = record.getMessage()
        assert "SECRET-VALUE" not in message
        assert text not in message


# --- lazy logging (PKG-03) -----------------------------------------------------

_LAZY = """
import json, sys
import locjson
before = "logging" in sys.modules
l10n = locjson.Localizer(loader=locjson.DictLoader({"en": {"g": "Hi {name}"}}))
for _ in range(50):
    l10n.t("missing")
    l10n.t("g")
import logging
handlers = [type(h).__name__ for h in logging.getLogger("locjson").handlers]
print(json.dumps({"before": before, "after": "logging" in sys.modules,
                  "handlers": handlers}))
"""


def test_logging_is_imported_lazily_on_the_first_slip() -> None:
    out = subprocess.run(
        [sys.executable, "-I", "-c", _LAZY],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    ).stdout
    result: dict[str, Any] = json.loads(out)
    assert result == {"before": False, "after": True, "handlers": ["NullHandler"]}
