"""CLDR plural operands for a count (Unicode TR35, "Plural Operand Meanings").

A plural rule never looks at the count itself, only at these operands:

* ``n``: the absolute value of the count.
* ``i``: the integer digits of ``n``.
* ``v``: the number of visible fraction digits, with trailing zeros.
* ``w``: the number of visible fraction digits, without trailing zeros.
* ``f``: the visible fraction digits, with trailing zeros, as an integer.
* ``t``: the visible fraction digits, without trailing zeros, as an integer.

The compact-exponent operands ``c`` and ``e`` are always 0, so they are not
stored. :mod:`decimal` is imported at module level: it is in the standard
library and loads none of the modules that ``import locjson`` must avoid.
"""

from __future__ import annotations

import collections
import math
import operator
from decimal import Decimal
from typing import TYPE_CHECKING, Final, cast

if TYPE_CHECKING:
    from typing import NamedTuple

    class _OperandFields(NamedTuple):
        n: int | Decimal
        i: int
        v: int
        w: int
        f: int
        t: int

else:
    # Class-syntax typing.NamedTuple imports ast on 3.14 (PKG-03).
    _OperandFields = collections.namedtuple("_OperandFields", "n i v w f t")

__all__ = ["MAX_COUNT_DIGITS", "Operands", "plural_operands"]

MAX_COUNT_DIGITS: Final = 1000
"""The most integer digits, and the most fraction digits, a count may have.

This is a resource bound, not a CLDR rule: it keeps operand derivation and
``{count}`` rendering small whatever value a caller passes.
"""

_INT_LIMIT: Final = 10**MAX_COUNT_DIGITS  # the smallest int with too many digits
_NOT_FINITE: Final = "count must be a finite number"
_TOO_MANY_DIGITS: Final = f"count has more than {MAX_COUNT_DIGITS} digits"


class Operands(_OperandFields):
    """The CLDR plural operands ``n i v w f t`` of one count (a ``NamedTuple``).

    Attributes:
        n: The absolute value of the count, an ``int`` or a ``Decimal``.
        i: The integer digits of ``n``.
        v: The number of visible fraction digits, with trailing zeros.
        w: The number of visible fraction digits, without trailing zeros.
        f: The visible fraction digits, with trailing zeros.
        t: The visible fraction digits, without trailing zeros.
    """

    __slots__ = ()


def plural_operands(count: object) -> Operands:
    """Return the CLDR plural operands of ``count``.

    An ``int`` has no fraction digits. A ``Decimal`` keeps the fraction digits
    it was written with, so ``Decimal("1.50")`` has ``v = 2``, ``f = 50`` and
    ``t = 5``. A ``float`` is read through its shortest ``repr``: an integral
    float acts as the int, so ``1.0`` has ``v = 0``, and ``1.5`` has ``v = 1``.
    A subclass (NumPy's ``np.float64`` is one) is read through the ``float``
    value it holds; its own ``repr`` and arithmetic are never used.
    Negative counts use their absolute value.

    Error messages name the type or the problem, never the value, because a
    count may come from request input.

    Args:
        count: The quantity: an ``int`` (not a ``bool``), ``float`` or
            ``Decimal``, or an instance of a subclass of one of them.

    Returns:
        The operands.

    Raises:
        TypeError: If ``count`` is a ``bool`` or not an ``int``, ``float`` or
            ``Decimal``.
        ValueError: If ``count`` is NaN or infinite, or has more than
            :data:`MAX_COUNT_DIGITS` integer or fraction digits.
    """
    if isinstance(count, bool) or not isinstance(count, int | float | Decimal):
        msg = f"count must be an int, float or Decimal, not {type(count).__name__}"
        raise TypeError(msg)
    # The built-in methods are called unbound, so a subclass's own overrides
    # (NumPy's np.float64 has its own __abs__ and __repr__) never run here.
    if isinstance(count, int):
        n = abs(operator.index(count))  # an exact int, without calling __int__
        if n >= _INT_LIMIT:
            raise ValueError(_TOO_MANY_DIGITS)
        return Operands(n, n, 0, 0, 0, 0)
    if isinstance(count, float):
        value = abs(float.__float__(count))  # an exact float
        if not math.isfinite(value):
            raise ValueError(_NOT_FINITE)
        if value.is_integer():  # at most 309 digits
            n = int(value)
            return Operands(n, n, 0, 0, 0, 0)
        # The shortest text that round-trips, so 1.5 reads as "1.5". repr() of
        # a subclass may not be a number at all ("np.float64(1.5)").
        return _decimal_operands(Decimal(float.__repr__(value)))
    # copy_abs, not abs(): abs() rounds to the context precision.
    return _decimal_operands(Decimal.copy_abs(count))


def _decimal_operands(n: Decimal) -> Operands:
    # Checked before anything else: comparing a signalling NaN raises.
    if not n.is_finite():
        raise ValueError(_NOT_FINITE)
    _, digits, exponent = n.as_tuple()
    exponent = cast("int", exponent)  # a str only for NaN and infinities
    # Checked before int(n): int(Decimal("1e999999999")) would not finish.
    if n.adjusted() >= MAX_COUNT_DIGITS or exponent < -MAX_COUNT_DIGITS:
        raise ValueError(_TOO_MANY_DIGITS)
    i = int(n)  # truncates toward zero, never rounds
    if exponent >= 0:
        return Operands(n, i, 0, 0, 0, 0)
    v = -exponent
    # The last v digits; fewer when the coefficient is shorter, and the
    # missing leading zeros change neither f nor t.
    fraction = "".join(map(str, digits[-v:]))
    stripped = fraction.rstrip("0")
    if not stripped:
        return Operands(n, i, v, 0, 0, 0)
    w = v - (len(fraction) - len(stripped))
    return Operands(n, i, v, w, int(fraction), int(stripped))
