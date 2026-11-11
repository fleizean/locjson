"""The ``locjson`` logger, created on first use, and slip reporting (internal).

``import logging`` is deferred to the first record: on Python 3.14 it pulls in
``ast`` through ``traceback``, which would break the lightweight-import
guarantee (PKG-03). A ``NullHandler`` is attached once, so applications that
never configure logging see no output.
"""

from __future__ import annotations

import functools
import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import logging

__all__ = ["SEEN_MAX", "SlipLog", "debug", "get_logger"]

_DEBUG = 10  # logging.DEBUG, without importing logging
_WARNING = 30  # logging.WARNING

SEEN_MAX = 1024
"""How many ``(kind, locale, key)`` slips a :class:`SlipLog` remembers."""


@functools.cache
def get_logger() -> logging.Logger:
    """Return the ``locjson`` logger, importing :mod:`logging` on first use.

    Returns:
        The ``locjson`` logger, with one ``NullHandler`` attached.
    """
    # Deferred on purpose: on 3.14 logging imports ast (PKG-03). Ruff's TID253
    # bans it at module level, which also exempts this import from PLC0415.
    import logging

    logger = logging.getLogger("locjson")
    if not any(isinstance(handler, logging.NullHandler) for handler in logger.handlers):
        logger.addHandler(logging.NullHandler())
    return logger


def debug(msg: str, *args: object) -> None:
    """Emit a DEBUG record on ``locjson`` when that level is enabled.

    Args:
        msg: A ``%``-style format string, formatted only when emitted.
        *args: The format arguments.
    """
    logger = get_logger()
    if logger.isEnabledFor(_DEBUG):
        logger.debug(msg, *args)


class SlipLog:
    """Logs translation slips: WARNING the first time, DEBUG afterwards.

    A slip is identified by ``(kind, locale, key)``. The first occurrence is
    logged at WARNING so it shows up with a default logging setup, and repeats
    drop to DEBUG so a hot path cannot flood the log. The store of seen slips
    is bounded at :data:`SEEN_MAX` entries; the oldest is forgotten first.

    Records carry only kinds, keys, locale tags and placeholder names, never
    variable values or rendered text.
    """

    __slots__ = ("_lock", "_seen")

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # Insertion-ordered set: the first key is the oldest entry.
        self._seen: dict[tuple[str, str, str], None] = {}

    def report(self, kind: str, locale: str, key: str, msg: str, *args: object) -> None:
        """Log one slip at WARNING if it is new, else at DEBUG.

        Args:
            kind: The kind of slip, such as ``"missing key"``.
            locale: The canonical locale of the lookup.
            key: The translation key.
            msg: A ``%``-style format string, formatted only when emitted.
            *args: The format arguments.
        """
        marker = (kind, locale, key)
        with self._lock:
            new = marker not in self._seen
            if new:
                if len(self._seen) >= SEEN_MAX:
                    del self._seen[next(iter(self._seen))]
                self._seen[marker] = None
        level = _WARNING if new else _DEBUG
        logger = get_logger()
        if logger.isEnabledFor(level):
            logger.log(level, msg, *args)

    def variable(self, key: str, locale: str, name: str) -> None:
        """Report a placeholder rendered without a value.

        Args:
            key: The translation key.
            locale: The canonical locale of the lookup.
            name: The placeholder name.
        """
        self.report(
            "missing variable",
            locale,
            key,
            "locjson: missing variable %r for key %r in %r",
            name,
            key,
            locale,
        )
