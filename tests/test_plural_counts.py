"""Count semantics through ``t()``: float/Decimal (ROADMAP SC2) and invalid counts."""

from __future__ import annotations

import decimal
import logging
from decimal import Decimal
from fractions import Fraction
from typing import TYPE_CHECKING, Any

import pytest

import locjson
import locjson.localizer
from locjson import (
    DictLoader,
    InterpolationError,
    Localizer,
    LocJsonError,
    MissingTranslationError,
)
from locjson._compat import override

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping

    from locjson.localizer import MissingPolicy
    from locjson.plural.operands import Operands

_X = {"x": {"one": "one {count}", "other": "other {count}"}}


class NumpyLikeFloat(float):
    """Behaves like NumPy 2's ``np.float64``: ``repr()`` is not a plain number."""

    @override
    def __abs__(self) -> NumpyLikeFloat:
        return NumpyLikeFloat(float.__abs__(self))

    @override
    def __repr__(self) -> str:
        return f"np.float64({float.__repr__(self)})"

    @override
    def __str__(self) -> str:
        return float.__repr__(self)


def _l10n(
    catalogs: Mapping[str, Mapping[str, object]] | None = None,
    *,
    missing: MissingPolicy = "key",
    strict: bool | None = None,
) -> Localizer:
    return Localizer(
        loader=DictLoader({"en": _X} if catalogs is None else catalogs),
        missing=missing,
        strict=strict,
    )


def _records(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [record for record in caplog.records if record.name == "locjson"]


@pytest.fixture(autouse=True)
def _no_default_localizer() -> Iterator[None]:
    locjson._DEFAULT.localizer = None
    yield
    locjson._DEFAULT.localizer = None


# --- ROADMAP SC2: float and Decimal -------------------------------------------


def test_decimal_one_point_zero_differs_between_english_and_turkish() -> None:
    l10n = _l10n({"en": _X, "tr": {"x": {"one": "bir {count}", "other": "diger"}}})
    assert l10n.t("x", count=Decimal("1.0")) == "other 1.0"
    assert l10n.t("x", locale="tr", count=Decimal("1.0")) == "bir 1.0"
    assert l10n.t("x", count=Decimal(1)) == "one 1"


def test_one_and_a_half_is_one_in_french_and_other_in_english() -> None:
    l10n = _l10n({"en": _X, "fr": {"x": {"one": "un", "other": "autre"}}})
    assert l10n.t("x", locale="fr", count=1.5) == "un"
    assert l10n.t("x", count=1.5) == "other 1.5"


def test_float_count_renders_its_repr() -> None:
    l10n = _l10n()
    assert l10n.t("x", count=0.1 + 0.2) == "other 0.30000000000000004"
    assert l10n.t("x", count=1.0) == "one 1.0"
    assert l10n.t("x", count=-1) == "one -1"
    assert l10n.t("x", count=Decimal(-1)) == "one -1"


def test_zero_override_for_negative_and_decimal_zeros() -> None:
    l10n = _l10n({"en": {"x": {"zero": "none", "other": "{count}"}}})
    for count in (-0.0, 0.0, Decimal("-0.00"), Decimal("0E+3")):
        assert l10n.t("x", count=count) == "none"


def test_numpy_like_float_counts_pick_the_cldr_form() -> None:
    # CR-01: a non-integral np.float64 made t() raise decimal.InvalidOperation.
    l10n = _l10n({"en": _X, "fr": {"x": {"one": "un {count}", "other": "autre"}}})
    assert l10n.t("x", locale="fr", count=NumpyLikeFloat(1.5)) == "un 1.5"
    assert l10n.t("x", count=NumpyLikeFloat(-1.5)) == "other -1.5"
    assert l10n.t("x", count=NumpyLikeFloat(1.0)) == "one 1.0"
    strict = _l10n(strict=True)
    assert strict.t("x", count=NumpyLikeFloat(2.5)) == "other 2.5"


class IndexCount:
    """An integer type that is not an ``int``, like NumPy's ``np.int64``."""

    __slots__ = ("value",)

    def __init__(self, value: int) -> None:
        self.value = value

    def __index__(self) -> int:
        return self.value

    @override
    def __str__(self) -> str:
        return str(self.value)


def test_integer_types_with_index_are_counts() -> None:
    # IN-03: np.int64 is not an int subclass, but it is an integer.
    ru = {"one": "{count} one", "few": "{count} few", "many": "{count} many"}
    l10n = _l10n({"en": _X, "ru": {"x": {**ru, "other": "other"}}})
    assert l10n.t("x", count=IndexCount(1)) == "one 1"
    assert l10n.t("x", count=IndexCount(-7)) == "other -7"
    assert l10n.t("x", locale="ru", count=IndexCount(2)) == "2 few"
    assert l10n.t("x", locale="ru", count=IndexCount(5)) == "5 many"
    assert l10n.t("x", locale="ru", count=IndexCount(21)) == "21 one"
    assert _l10n(strict=True).t("x", count=IndexCount(2)) == "other 2"


def test_counts_at_the_digit_cap_render() -> None:
    big = 10**1000 - 1
    l10n = _l10n()
    assert l10n.t("x", count=big) == f"other {big}"
    assert l10n.t("x", count=Decimal(10**999)) == f"other {10**999}"
    tiny = Decimal("1e-1000")
    assert l10n.t("x", count=tiny) == f"other {tiny}"


# --- invalid counts are slips -------------------------------------------------

INVALID: list[Any] = [
    True,
    False,
    "3",
    float("nan"),
    float("inf"),
    float("-inf"),
    Decimal("sNaN"),
    Decimal("NaN"),
    Decimal("Infinity"),
    10**1000,
    Decimal("1e-1001"),
    Fraction(1, 2),
    complex(1),
    object(),
]
INVALID_IDS = [
    "True",
    "False",
    "str",
    "nan",
    "inf",
    "-inf",
    "sNaN",
    "Decimal-NaN",
    "Decimal-inf",
    "big-int",
    "long-fraction",
    "Fraction",
    "complex",
    "object",
]


@pytest.mark.parametrize("count", INVALID, ids=INVALID_IDS)
def test_lenient_invalid_count_uses_other_and_logs_once(
    count: Any, caplog: pytest.LogCaptureFixture
) -> None:
    l10n = _l10n()
    with caplog.at_level(logging.DEBUG, logger="locjson"):
        first = l10n.t("x", count=count)
        second = l10n.t("x", count=count)
    assert first == second == "other {count}"
    records = _records(caplog)
    assert [record.levelname for record in records] == ["WARNING", "DEBUG"]
    for record in records:
        message = record.getMessage()
        assert "invalid count" in message
        assert "'x'" in message
        assert "'en'" in message


def test_invalid_count_on_a_plain_entry(caplog: pytest.LogCaptureFixture) -> None:
    l10n = _l10n({"en": {"n": "{count} left"}})
    with caplog.at_level(logging.DEBUG, logger="locjson"):
        assert l10n.t("n", count="3") == "{count} left"  # type: ignore[arg-type]
    messages = [record.getMessage() for record in _records(caplog)]
    assert len(messages) == 1
    assert "invalid count" in messages[0]
    assert not any("missing variable" in message for message in messages)


@pytest.mark.parametrize(
    "error",
    [decimal.InvalidOperation, OverflowError, ZeroDivisionError],
    ids=["InvalidOperation", "OverflowError", "ZeroDivisionError"],
)
def test_arithmetic_errors_from_operands_are_invalid_count_slips(
    error: type[ArithmeticError],
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Defense in depth (CR-01): whatever a numeric type does, an
    # ArithmeticError never escapes t(), and its text is never shown.
    def broken(count: object) -> Operands:
        raise error("SECRET-VALUE")

    monkeypatch.setattr(locjson.localizer, "plural_operands", broken)
    with caplog.at_level(logging.DEBUG, logger="locjson"):
        assert _l10n().t("x", count=2) == "other {count}"
    records = _records(caplog)
    assert [record.levelname for record in records] == ["WARNING"]
    assert "invalid count" in records[0].getMessage()
    assert "SECRET" not in records[0].getMessage()
    for l10n in (_l10n(strict=True), _l10n(missing="raise")):
        with pytest.raises(InterpolationError) as info:
            l10n.t("x", count=2)
        assert info.value.name == "count"
        assert "SECRET" not in str(info.value)


def test_invalid_count_still_reports_other_missing_names(
    caplog: pytest.LogCaptureFixture,
) -> None:
    l10n = _l10n({"en": {"x": {"one": "a", "other": "{count} {who} {what}"}}})
    with caplog.at_level(logging.DEBUG, logger="locjson"):
        text = l10n.t("x", count=True, what="W")
    assert text == "{count} {who} W"
    messages = [record.getMessage() for record in _records(caplog)]
    assert len(messages) == 2
    assert "invalid count" in messages[0]
    assert "missing variable 'who'" in messages[1]


def test_invalid_count_values_never_reach_logs_or_errors(
    caplog: pytest.LogCaptureFixture,
) -> None:
    private: Any = "SECRET-VALUE"
    with caplog.at_level(logging.DEBUG, logger="locjson"):
        assert _l10n().t("x", count=private) == "other {count}"
        assert _l10n({"en": {"n": "{count}"}}).t("n", count=private) == "{count}"
    for strict in (True, False):
        l10n = _l10n(strict=strict, missing="raise")
        with pytest.raises(InterpolationError) as info:
            l10n.t("x", count=private)
        assert "SECRET" not in str(info.value)
        assert "SECRET" not in repr(info.value.args)
    records = _records(caplog)
    assert records
    for record in records:
        assert "SECRET" not in record.getMessage()


def test_missing_key_with_an_invalid_count_reports_the_missing_key_only(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.DEBUG, logger="locjson"):
        assert _l10n().t("nope", count="3") == "nope"  # type: ignore[arg-type]
    messages = [record.getMessage() for record in _records(caplog)]
    assert len(messages) == 1
    assert "missing key" in messages[0]
    with pytest.raises(MissingTranslationError):
        _l10n(missing="raise").t("nope", count="3")  # type: ignore[arg-type]


# --- strict: InterpolationError -------------------------------------------------


@pytest.mark.parametrize("key", ["x", "n"])
@pytest.mark.parametrize(
    "options",
    [{"strict": True}, {"missing": "raise"}],
    ids=["strict", "missing-raise"],
)
def test_strict_invalid_count_raises(key: str, options: dict[str, Any]) -> None:
    l10n = _l10n({"en": {**_X, "n": "{count} left"}}, **options)
    with pytest.raises(InterpolationError) as info:
        l10n.t(key, count="3")  # type: ignore[arg-type]
    error = info.value
    assert isinstance(error, LocJsonError)
    assert error.key == key
    assert error.name == "count"
    assert key in str(error)
    assert l10n.t(key, count=2) in {"other 2", "2 left"}


@pytest.mark.parametrize("count", INVALID, ids=INVALID_IDS)
def test_every_invalid_count_raises_when_strict(count: Any) -> None:
    with pytest.raises(InterpolationError):
        _l10n(strict=True).t("x", count=count)


# --- the same through Translator and the module API ------------------------------


def test_translator_and_module_api_treat_invalid_counts_the_same() -> None:
    l10n = locjson.setup(loader=DictLoader({"en": _X}))
    assert l10n.for_locale("en")("x", count=True) == "other {count}"
    assert locjson.t("x", count=float("nan")) == "other {count}"
    assert locjson.t("x", count=Decimal("1.0")) == "other 1.0"
    strict = locjson.setup(loader=DictLoader({"en": _X}), strict=True)
    with pytest.raises(InterpolationError):
        strict.for_locale("en")("x", count="3")  # type: ignore[arg-type]
    with pytest.raises(InterpolationError):
        locjson.t("x", count="3")  # type: ignore[arg-type]
