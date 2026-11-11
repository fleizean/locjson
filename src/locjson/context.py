"""The current locale of one :class:`~locjson.Localizer`, held in a ContextVar."""

from __future__ import annotations

import contextlib
import contextvars
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator

__all__ = ["LocaleContext"]


class LocaleContext:
    """A per-Localizer :class:`~contextvars.ContextVar` holding a locale tag.

    Each instance owns its own variable, so two Localizers never share a
    current locale. The value is per context: every asyncio task works on a
    copy of the context it was created in, and every thread starts from an
    empty context (on free-threaded builds with ``thread_inherit_context``, a
    new thread starts from a copy of its creator's context instead).
    ``None`` means "no locale set".

    Caveats, inherent to context variables:

    - A thread-pool worker keeps a value set with :meth:`set` for the next job
      it runs. Prefer :meth:`use`, which restores the previous value.
    - A ``with use(...)`` block inside a generator or async generator stays in
      effect for the caller's frame while the generator is suspended.
    """

    __slots__ = ("_var",)

    def __init__(self) -> None:
        # One variable per Localizer: the owning Localizer keeps it alive.
        self._var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
            "locjson.locale", default=None
        )

    def get(self) -> str | None:
        """Return the locale set in the current context, or ``None``."""
        return self._var.get()

    def set(self, tag: str | None) -> None:
        """Set the locale for the rest of the current context.

        Args:
            tag: A canonical locale tag, or ``None`` to clear it.
        """
        self._var.set(tag)

    @contextlib.contextmanager
    def use(self, tag: str | None) -> Iterator[None]:
        """Set the locale for the duration of a ``with`` block.

        On exit the previous value is restored through the token, including
        the unset state. When the block is left in another context than it was
        entered in (an async generator closed from another task), resetting
        the token is impossible, so the token's previous value is set again
        instead of raising.

        Args:
            tag: A canonical locale tag, or ``None`` for the default.

        Yields:
            Nothing; the locale is in effect inside the block.
        """
        token = self._var.set(tag)
        try:
            yield
        finally:
            try:
                self._var.reset(token)
            except ValueError:
                old = token.old_value
                self._var.set(None if old is contextvars.Token.MISSING else old)
