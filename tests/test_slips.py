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
    _log,
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


def _levels(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [record.levelname for record in _records(caplog)]


def test_missing_key_warns_once_then_logs_debug(
    sample_catalogs: Catalogs, caplog: pytest.LogCaptureFixture
) -> None:
    l10n = _l10n(sample_catalogs)
    with caplog.at_level(logging.DEBUG, logger="locjson"):
        l10n.t("nope", locale="tr")
        l10n.t("nope", locale="tr")
    assert _levels(caplog) == ["WARNING", "DEBUG"]
    message = _records(caplog)[0].getMessage()
    assert "missing key" in message
    assert "'nope'" in message
    assert "'tr'" in message


def test_a_new_key_locale_or_kind_warns_again(
    sample_catalogs: Catalogs, caplog: pytest.LogCaptureFixture
) -> None:
    l10n = _l10n(sample_catalogs)
    with caplog.at_level(logging.DEBUG, logger="locjson"):
        l10n.t("nope")  # missing key in en
        l10n.t("nope", locale="tr")  # another locale
        l10n.t("nope2")  # another key
        l10n.t("greeting")  # another kind: missing variable
        l10n.t("greeting")
        l10n.t("inbox.messages")  # missing count
        l10n.t("inbox.messages")
    assert _levels(caplog) == [
        "WARNING",
        "WARNING",
        "WARNING",
        "WARNING",
        "DEBUG",
        "WARNING",
        "DEBUG",
    ]


def test_dedupe_is_per_localizer(
    sample_catalogs: Catalogs, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.DEBUG, logger="locjson"):
        _l10n(sample_catalogs).t("nope")
        _l10n(sample_catalogs).t("nope")
    assert _levels(caplog) == ["WARNING", "WARNING"]


def test_dedupe_store_is_bounded_fifo(
    sample_catalogs: Catalogs, caplog: pytest.LogCaptureFixture
) -> None:
    l10n = _l10n(sample_catalogs)
    for index in range(1100):
        l10n.t(f"missing.{index}")
    assert len(l10n._slips._seen) <= 1024
    with caplog.at_level(logging.DEBUG, logger="locjson"):
        l10n.t("missing.0")  # evicted first, so it warns again
        l10n.t("missing.1099")  # still remembered
    assert _levels(caplog) == ["WARNING", "DEBUG"]


def test_invalid_request_locale_never_warns(
    sample_catalogs: Catalogs, caplog: pytest.LogCaptureFixture
) -> None:
    l10n = _l10n(sample_catalogs)
    with caplog.at_level(logging.DEBUG, logger="locjson"):
        for _ in range(3):
            assert l10n.t("nav.home", locale="../../etc") == "Home"
    assert _levels(caplog) == ["DEBUG", "DEBUG", "DEBUG"]


def test_warm_lookups_log_nothing(
    sample_catalogs: Catalogs, caplog: pytest.LogCaptureFixture
) -> None:
    l10n = _l10n(sample_catalogs)
    with caplog.at_level(logging.DEBUG, logger="locjson"):
        l10n.t("greeting", name="Enes")
        l10n.t("inbox.messages", locale="tr", count=2)
        l10n.t("nav.home", locale="pt-BR")
    assert _records(caplog) == []


# --- missing variables (INT-03) ------------------------------------------------


def test_missing_variable_keeps_the_placeholder(
    sample_catalogs: Catalogs, caplog: pytest.LogCaptureFixture
) -> None:
    l10n = _l10n(sample_catalogs)
    with caplog.at_level(logging.DEBUG, logger="locjson"):
        assert l10n.t("greeting", locale="tr") == "Merhaba, {name}!"
    records = _records(caplog)
    assert len(records) == 1
    message = records[0].getMessage()
    assert "missing variable" in message
    assert "'name'" in message
    assert "'greeting'" in message
    assert "'tr'" in message


def test_missing_variable_record_names_the_variable_not_other_values(
    caplog: pytest.LogCaptureFixture,
) -> None:
    l10n = _l10n({"en": {"card": "{who} paid {amount}"}})
    with caplog.at_level(logging.DEBUG, logger="locjson"):
        l10n.t("card", who="Ayşe Yılmaz")
    (record,) = _records(caplog)
    assert "'amount'" in record.getMessage()
    assert "Ayşe" not in record.getMessage()
    assert record.args is not None
    assert "Ayşe Yılmaz" not in repr(record.args)


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
    (record,) = _records(caplog)
    assert "missing count" in record.getMessage()
    assert "'inbox.messages'" in record.getMessage()


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


def test_get_logger_attaches_a_single_null_handler() -> None:
    _log.get_logger.cache_clear()
    logger = _log.get_logger()
    _log.get_logger.cache_clear()  # a racing first call runs the body again
    assert _log.get_logger() is logger
    nulls = [h for h in logger.handlers if isinstance(h, logging.NullHandler)]
    assert len(nulls) == 1


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
