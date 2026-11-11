"""CLDR TR35 plural operands for int, float and Decimal counts (PLUR-02)."""

from __future__ import annotations

from decimal import Decimal
from fractions import Fraction

import pytest

from locjson.plural.operands import MAX_COUNT_DIGITS, Operands, plural_operands


@pytest.mark.parametrize(
    ("count", "expected"),
    [
        (1, (1, 1, 0, 0, 0, 0)),
        (1.0, (1, 1, 0, 0, 0, 0)),
        (0, (0, 0, 0, 0, 0, 0)),
        (Decimal("1.0"), (Decimal("1.0"), 1, 1, 0, 0, 0)),
        (Decimal("1.00"), (Decimal("1.00"), 1, 2, 0, 0, 0)),
        (Decimal("1.3"), (Decimal("1.3"), 1, 1, 1, 3, 3)),
        (Decimal("1.30"), (Decimal("1.30"), 1, 2, 1, 30, 3)),
        (Decimal("1.03"), (Decimal("1.03"), 1, 2, 2, 3, 3)),
        (Decimal("1.230"), (Decimal("1.230"), 1, 3, 2, 230, 23)),
        (Decimal("1.50"), (Decimal("1.50"), 1, 2, 1, 50, 5)),
        (1.5, (Decimal("1.5"), 1, 1, 1, 5, 5)),
        (Decimal("0.05"), (Decimal("0.05"), 0, 2, 2, 5, 5)),
        (Decimal("0.00"), (Decimal("0.00"), 0, 2, 0, 0, 0)),
        (Decimal("1E+3"), (Decimal("1E+3"), 1000, 0, 0, 0, 0)),
        (-1, (1, 1, 0, 0, 0, 0)),
        (Decimal("-2.50"), (Decimal("2.50"), 2, 2, 1, 50, 5)),
        (Decimal(-1), (Decimal(1), 1, 0, 0, 0, 0)),
        (-0.0, (0, 0, 0, 0, 0, 0)),
        (1e16, (10**16, 10**16, 0, 0, 0, 0)),
    ],
)
def test_operand_table(count: float | Decimal, expected: tuple[object, ...]) -> None:
    operands = plural_operands(count)
    assert isinstance(operands, Operands)
    assert tuple(operands) == expected
    assert operands.n == expected[0]


def test_operand_fields_are_named() -> None:
    operands = plural_operands(Decimal("12.340"))
    assert (operands.n, operands.i, operands.v) == (Decimal("12.340"), 12, 3)
    assert (operands.w, operands.f, operands.t) == (2, 340, 34)
    assert Operands._fields == ("n", "i", "v", "w", "f", "t")


def test_negative_decimal_keeps_its_digits() -> None:
    operands = plural_operands(Decimal("-2.50"))
    assert str(operands.n) == "2.50"


def test_float_uses_its_shortest_repr() -> None:
    operands = plural_operands(0.1 + 0.2)
    assert operands.v == 17
    assert operands.i == 0
    assert operands.f == 30000000000000004
    assert plural_operands(1e16).v == 0
    assert plural_operands(1e-5).v == 5
    assert plural_operands(1e-5).f == 1


def test_decimal_is_never_rounded_to_the_context() -> None:
    text = "123456789012345678901234567890123456789.5"
    assert len(text.replace(".", "")) == 40
    operands = plural_operands(Decimal("-" + text))
    assert str(operands.n) == text
    assert operands.i == 123456789012345678901234567890123456789
    assert (operands.v, operands.f) == (1, 5)


def test_int_subclasses_are_counts() -> None:
    class Count(int):
        pass

    assert plural_operands(Count(-3)) == (3, 3, 0, 0, 0, 0)
    assert type(plural_operands(Count(3)).n) is int


@pytest.mark.parametrize(
    "count",
    [True, False, "3", None, Fraction(1, 2), complex(1), object(), b"1", [1]],
    ids=[
        "True",
        "False",
        "str",
        "None",
        "Fraction",
        "complex",
        "object",
        "bytes",
        "list",
    ],
)
def test_non_numbers_are_type_errors(count: object) -> None:
    with pytest.raises(TypeError, match="count must be an int, float or Decimal"):
        plural_operands(count)


def test_bool_is_named_in_the_error() -> None:
    with pytest.raises(TypeError, match="not bool"):
        plural_operands(True)


@pytest.mark.parametrize(
    "count",
    [
        float("nan"),
        float("inf"),
        float("-inf"),
        Decimal("NaN"),
        Decimal("sNaN"),
        Decimal("Infinity"),
        Decimal("-Infinity"),
    ],
    ids=[
        "nan",
        "inf",
        "-inf",
        "Decimal-NaN",
        "Decimal-sNaN",
        "Decimal-inf",
        "Decimal--inf",
    ],
)
def test_non_finite_counts_are_value_errors(count: float | Decimal) -> None:
    with pytest.raises(ValueError, match="finite"):
        plural_operands(count)


@pytest.mark.parametrize(
    "count",
    [
        10**MAX_COUNT_DIGITS,
        -(10**MAX_COUNT_DIGITS),
        Decimal(10**MAX_COUNT_DIGITS),
        Decimal("1e1000"),
        Decimal("1e-1001"),
        Decimal("1e999999999"),
        Decimal("0E-1001"),
    ],
    ids=[
        "int",
        "-int",
        "Decimal-int",
        "Decimal-exp",
        "fraction",
        "huge-exp",
        "zero-exp",
    ],
)
def test_counts_beyond_the_digit_cap_are_value_errors(count: int | Decimal) -> None:
    with pytest.raises(ValueError, match=f"more than {MAX_COUNT_DIGITS} digits"):
        plural_operands(count)


def test_counts_at_the_digit_cap_are_accepted() -> None:
    assert MAX_COUNT_DIGITS == 1000
    largest = 10**MAX_COUNT_DIGITS - 1
    assert len(str(largest)) == 1000
    assert plural_operands(largest).i == largest
    assert plural_operands(-largest).n == largest
    assert plural_operands(Decimal(10**999)).i == 10**999
    assert plural_operands(Decimal(largest)).i == largest
    smallest = plural_operands(Decimal("1e-1000"))
    assert (smallest.i, smallest.v, smallest.w, smallest.f, smallest.t) == (
        0,
        1000,
        1000,
        1,
        1,
    )


@pytest.mark.parametrize(
    "count",
    ["SECRET-VALUE", Decimal("NaN"), 10**MAX_COUNT_DIGITS, Fraction(7, 3)],
    ids=["str", "nan", "big", "fraction"],
)
def test_errors_never_show_the_value(count: object) -> None:
    with pytest.raises((TypeError, ValueError)) as info:
        plural_operands(count)
    message = str(info.value)
    assert "SECRET" not in message
    assert "7/3" not in message
    assert "1000000" not in message
    assert "NaN" not in message
