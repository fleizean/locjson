"""Catalog loaders: the :class:`Loader` protocol and its built-in variants."""

from __future__ import annotations

from locjson.loaders.base import Loader, RawSource
from locjson.loaders.filesystem import FilesystemLoader

__all__ = ["FilesystemLoader", "Loader", "RawSource"]
