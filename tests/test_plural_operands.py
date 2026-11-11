"""CLDR TR35 plural operands for int, float and Decimal counts (PLUR-02)."""

from __future__ import annotations

import decimal
from decimal import Decimal
from fractions import Fraction

import pytest

from locjson._compat import override
from locjson.plural.operands import MAX_COUNT_DIGITS, Operands, plural_operands


class NumpyLikeFloat(float):
    """Behaves like NumPy 2's ``np.float64``, a ``float`` subclass.

    ``abs()`` keeps the type, and ``repr()`` is not a plain number.
    """

    @override
    def __abs__(self) -> NumpyLikeFloat:
        return NumpyLikeFloat(float.__abs__(self))

    @override
    def __repr__(self) -> str:
        return f"np.float64({float.__repr__(self)})"

    @override
    def __str__(self) -> str:
        return float.__repr__(self)


class BrokenFloat(float):
    """A float subclass whose own arithmetic always fails."""

    @override
    def __float__(self) -> float:
        raise OverflowError

    @override
    def __abs__(self) -> float:
        raise OverflowError

    @override
    def is_integer(self) -> bool:
        raise OverflowError


class BrokenInt(int):
    """An int subclass whose own conversions always fail."""

    @override
    def __int__(self) -> int:
        raise OverflowError

    @override
    def __abs__(self) -> int:
        raise OverflowError


class BrokenDecimal(Decimal):
    """A Decimal subclass whose own methods always fail."""

    @override
    def copy_abs(self) -> Decimal:
        raise decimal.InvalidOperation

    @override
    def __abs__(self) -> Decimal:
        raise decimal.InvalidOperation


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


class IndexCount:
    """An integer type that is not an ``int``, like NumPy's ``np.int64``."""

    __slots__ = ("value",)

    def __init__(self, value: int) -> None:
        self.value = value

    def __index__(self) -> int:
        return self.value


class BrokenIndex:
    """An integer type whose ``__index__`` fails."""

    __slots__ = ("error",)

    def __init__(self, error: type[Exception]) -> None:
        self.error = error

    def __index__(self) -> int:
        raise self.error("SECRET-VALUE")


def test_integer_types_with_index_are_counts() -> None:
    # IN-03: np.int64 and friends are integers, read through operator.index().
    assert plural_operands(IndexCount(-3)) == (3, 3, 0, 0, 0, 0)
    assert type(plural_operands(IndexCount(3)).n) is int
    assert plural_operands(IndexCount(10**999)).i == 10**999


def test_integer_types_obey_the_digit_cap() -> None:
    with pytest.raises(ValueError, match=f"more than {MAX_COUNT_DIGITS} digits"):
        plural_operands(IndexCount(10**MAX_COUNT_DIGITS))


@pytest.mark.parametrize(
    "error",
    [TypeError, ValueError, OverflowError],
    ids=["TypeError", "ValueError", "OverflowError"],
)
def test_failing_index_is_a_type_error_without_the_value(
    error: type[Exception],
) -> None:
    with pytest.raises(TypeError, match="not BrokenIndex") as info:
        plural_operands(BrokenIndex(error))
    assert "SECRET" not in str(info.value)
    assert info.value.__cause__ is None
    assert info.value.__suppress_context__


def test_float_subclasses_use_the_shortest_repr_of_their_value() -> None:
    # NumPy 2: repr(np.float64(1.5)) == "np.float64(1.5)" (CR-01).
    assert plural_operands(NumpyLikeFloat(-1.5)) == (Decimal("1.5"), 1, 1, 1, 5, 5)
    assert plural_operands(NumpyLikeFloat(0.25)) == (Decimal("0.25"), 0, 2, 2, 25, 25)
    assert plural_operands(NumpyLikeFloat(-2.0)) == (2, 2, 0, 0, 0, 0)
    assert type(plural_operands(NumpyLikeFloat(1.5)).n) is Decimal


def test_numeric_subclass_overrides_are_never_called() -> None:
    # Operands come from the built-in value, so a subclass's own (here
    # failing) arithmetic can never raise out of plural_operands.
    assert plural_operands(BrokenFloat(-1.5)) == (Decimal("1.5"), 1, 1, 1, 5, 5)
    assert plural_operands(BrokenFloat(3.0)) == (3, 3, 0, 0, 0, 0)
    assert plural_operands(BrokenInt(-4)) == (4, 4, 0, 0, 0, 0)
    assert type(plural_operands(BrokenInt(4)).n) is int
    operands = plural_operands(BrokenDecimal("-2.50"))
    assert type(operands.n) is Decimal
    assert tuple(operands) == (Decimal("2.50"), 2, 2, 1, 50, 5)


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
