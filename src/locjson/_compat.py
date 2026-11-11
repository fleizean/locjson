"""Compatibility shims that keep ``import locjson`` dependency-free (internal).

``override`` is :func:`typing.override` on Python 3.12+ and a no-op decorator on
3.11. Type checkers always see ``typing_extensions.override``, which ships with
the type checker's bundled stubs, so it is never imported at runtime.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

__all__ = ["override"]

if TYPE_CHECKING:
    from typing_extensions import override
elif sys.version_info >= (3, 12):
    from typing import override
else:  # pragma: no cover - Python 3.11 only

    def override(method):
        return method
