"""Catalog loaders: the :class:`Loader` protocol and its built-in variants."""

from __future__ import annotations

from locjson.loaders.base import Loader, RawSource
from locjson.loaders.filesystem import FilesystemLoader
from locjson.loaders.memory import DictLoader

__all__ = ["DictLoader", "FilesystemLoader", "Loader", "RawSource"]
