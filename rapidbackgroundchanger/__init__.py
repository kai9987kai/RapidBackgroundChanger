"""Rapid Background Changer - rapidly cycle your desktop wallpaper.

Public API::

    from rapidbackgroundchanger import CycleEngine, Playlist, select_backend

    engine = CycleEngine(select_backend(), Playlist(paths), interval=0.1)
    engine.start()
    ...
    engine.stop()

The GUI lives in :mod:`rapidbackgroundchanger.gui` and is imported lazily so
that the rest of the package works without tkinter.
"""

from __future__ import annotations

__version__ = "2.0.0"

from .backends import (
    BackendUnavailable,
    NullBackend,
    WallpaperBackend,
    available_backends,
    select_backend,
)
from .engine import SAFE_MIN_INTERVAL, CycleEngine, CycleStats, EngineState
from .sources import NoImagesFound, Playlist, default_images, discover_images

__all__ = [
    "__version__",
    "BackendUnavailable",
    "CycleEngine",
    "CycleStats",
    "EngineState",
    "NoImagesFound",
    "NullBackend",
    "Playlist",
    "SAFE_MIN_INTERVAL",
    "WallpaperBackend",
    "available_backends",
    "default_images",
    "discover_images",
    "select_backend",
]
