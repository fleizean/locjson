"""Exception hierarchy and catalog issue records.

Every error locjson raises derives from :class:`LocJsonError`. The concrete
classes also derive from the matching builtin (``ValueError`` or
``LookupError``), so callers can catch either.
"""

from __future__ import annotations

import collections
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable
    from typing import NamedTuple

    class _CatalogIssueFields(NamedTuple):
        path: str
        pointer: str
        problem: str
        locale: str | None = None
        other_path: str | None = None
        other_pointer: str | None = None

else:
    # Class-syntax typing.NamedTuple imports annotationlib -> ast on Python 3.14,
    # which breaks the lightweight-import guarantee (PKG-03). The functional
    # collections.namedtuple builds the same tuple type without it.
    _CatalogIssueFields = collections.namedtuple(
        "_CatalogIssueFields",
        ["path", "pointer", "problem", "locale", "other_path", "other_pointer"],
        defaults=(None, None, None),
    )

__all__ = [
    "CatalogIssue",
    "ConfigurationError",
    "InterpolationError",
    "InvalidCatalogError",
    "InvalidLocaleError",
    "LocJsonError",
    "MissingTranslationError",
]


class LocJsonError(Exception):
    """Base class for every error raised by locjson."""


class ConfigurationError(LocJsonError, ValueError):
    """Raised when a :class:`~locjson.Localizer` is configured incorrectly."""


class InvalidLocaleError(LocJsonError, ValueError):
    """Raised when a locale tag cannot be normalized.

    Attributes:
        tag: The rejected input, exactly as it was given.
    """

    def __init__(self, tag: object, message: str | None = None) -> None:
        self.tag = tag
        super().__init__(message or f"invalid locale tag: {tag!r}")


class CatalogIssue(_CatalogIssueFields):
    """One problem found in a catalog (a ``NamedTuple``).

    Attributes:
        path: POSIX-style path of the file, relative to the catalog root
            (or ``"<dict>/<tag>"`` for in-memory catalogs).
        pointer: RFC 6901 JSON pointer to the offending value. ``""`` means
            the whole document.
        problem: Human-readable description of the problem.
        locale: Canonical locale the file belongs to, when known.
        other_path: Path of the conflicting file, for collisions.
        other_pointer: Pointer of the conflicting value, for collisions.
    """

    __slots__ = ()

    def format(self) -> str:
        """Render the issue as a single diagnostic line.

        Returns:
            ``"{path}: {pointer}: {problem}"``, or ``"{path}: {problem}"`` when
            the pointer is empty, followed by
            ``" (conflicts with {other_path}: {other_pointer})"`` when the issue
            names a conflicting location.
        """
        text = (
            f"{self.path}: {self.pointer}: {self.problem}"
            if self.pointer
            else f"{self.path}: {self.problem}"
        )
        if self.other_path is not None:
            other = (
                f"{self.other_path}: {self.other_pointer}"
                if self.other_pointer
                else self.other_path
            )
            text += f" (conflicts with {other})"
        return text


class InvalidCatalogError(LocJsonError, ValueError):
    """Raised when a catalog file or mapping is not valid.

    The message is :meth:`CatalogIssue.format` of the error's own fields. When
    the error summarizes several issues, `` (and N more)`` is appended and the
    full list is kept in :attr:`issues`.

    Attributes:
        problem: Human-readable description of the first problem.
        path: Path of the offending file, relative to the catalog root.
        pointer: RFC 6901 pointer to the offending value (``""`` = whole file).
        locale: Canonical locale of the file, when known.
        other_path: Path of the conflicting file, for collisions.
        other_pointer: Pointer of the conflicting value, for collisions.
        issues: Every issue this error reports, in deterministic order. Holds
            just this error's own issue when it was raised directly.
    """

    def __init__(
        self,
        problem: str,
        *,
        path: str,
        pointer: str = "",
        locale: str | None = None,
        other_path: str | None = None,
        other_pointer: str | None = None,
        issues: Iterable[CatalogIssue] = (),
    ) -> None:
        self.problem = problem
        self.path = path
        self.pointer = pointer
        self.locale = locale
        self.other_path = other_path
        self.other_pointer = other_pointer
        own = CatalogIssue(path, pointer, problem, locale, other_path, other_pointer)
        self.issues: tuple[CatalogIssue, ...] = tuple(issues) or (own,)
        message = own.format()
        if len(self.issues) > 1:
            message += f" (and {len(self.issues) - 1} more)"
        super().__init__(message)

    @classmethod
    def from_issues(cls, issues: Iterable[CatalogIssue]) -> InvalidCatalogError:
        """Build one error that reports a group of issues.

        Args:
            issues: The issues to report. Must not be empty.

        Returns:
            An error carrying the first issue in ``(path, pointer)`` order as
            its own fields, with every issue kept in :attr:`issues`.

        Raises:
            ValueError: If ``issues`` is empty.
        """
        collected = tuple(issues)
        if not collected:
            msg = "from_issues() needs at least one issue"
            raise ValueError(msg)
        first = min(collected, key=lambda issue: (issue.path, issue.pointer))
        return cls(
            first.problem,
            path=first.path,
            pointer=first.pointer,
            locale=first.locale,
            other_path=first.other_path,
            other_pointer=first.other_pointer,
            issues=collected,
        )


class MissingTranslationError(LocJsonError, LookupError):
    """Raised for a missing key under ``missing="raise"``.

    It is a ``LookupError`` but deliberately not a ``KeyError``.

    Attributes:
        key: The key that was looked up.
        locale: The resolved locale the lookup started from.
    """

    def __init__(self, key: str, locale: str) -> None:
        self.key = key
        self.locale = locale
        super().__init__(f"no translation for {key!r} in locale {locale!r}")


class InterpolationError(LocJsonError, ValueError):
    """Raised when a placeholder has no value under ``missing="raise"``.

    Attributes:
        key: The translation key whose template was rendered.
        name: The placeholder that had no value.
    """

    def __init__(self, key: str, name: str, message: str | None = None) -> None:
        self.key = key
        self.name = name
        super().__init__(message or f"no value for placeholder {{{name}}} in {key!r}")
