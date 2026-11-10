"""Typed, zero-dependency JSON localization for Python."""

from __future__ import annotations

from locjson._version import __version__
from locjson.errors import (
    ConfigurationError,
    InterpolationError,
    InvalidCatalogError,
    InvalidLocaleError,
    LocJsonError,
    MissingTranslationError,
)
from locjson.loaders import FilesystemLoader, Loader, RawSource
from locjson.localizer import Localizer

__all__ = [
    "ConfigurationError",
    "FilesystemLoader",
    "InterpolationError",
    "InvalidCatalogError",
    "InvalidLocaleError",
    "Loader",
    "LocJsonError",
    "Localizer",
    "MissingTranslationError",
    "RawSource",
    "__version__",
]
