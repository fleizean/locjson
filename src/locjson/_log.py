"""The ``locjson`` logger, created on first use (internal).

``import logging`` is deferred to the first record: on Python 3.14 it pulls in
``ast`` through ``traceback``, which would break the lightweight-import
guarantee (PKG-03). A ``NullHandler`` is attached once, so applications that
never configure logging see no output.
"""

from __future__ import annotations

import functools
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import logging

__all__ = ["debug", "get_logger"]

_DEBUG = 10  # logging.DEBUG, without importing logging


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
