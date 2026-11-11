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
    Negative counts use their absolute value.

    Args:
        count: The quantity: an ``int``, ``float`` or ``Decimal``.

    Returns:
        The operands.

    Raises:
        TypeError: If ``count`` is not an ``int``, ``float`` or ``Decimal``.
        ValueError: If ``count`` is not a finite number.
    """
    if type(count) is int:  # the common case, without isinstance chains
        n = abs(count)
        return Operands(n, n, 0, 0, 0, 0)
    if isinstance(count, int):
        n = abs(int(count))
        return Operands(n, n, 0, 0, 0, 0)
    if isinstance(count, float):
        if count.is_integer():
            n = int(abs(count))
            return Operands(n, n, 0, 0, 0, 0)
        # repr is the shortest text that round-trips, so 1.5 reads as "1.5".
        return _decimal_operands(Decimal(repr(abs(count))))
    if isinstance(count, Decimal):
        # copy_abs, not abs(): abs() rounds to the context precision.
        return _decimal_operands(count.copy_abs())
    msg = f"count must be an int, float or Decimal, not {type(count).__name__}"
    raise TypeError(msg)


def _decimal_operands(n: Decimal) -> Operands:
    # Checked before anything else: comparing a signalling NaN raises.
    if not n.is_finite():
        msg = "count must be a finite number"
        raise ValueError(msg)
    _, digits, exponent = n.as_tuple()
    exponent = cast("int", exponent)  # a str only for NaN and infinities
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
