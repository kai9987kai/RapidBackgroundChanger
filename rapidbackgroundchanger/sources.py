"""Finding images and ordering them into a playlist.

The original script hard-coded six file names under ``C:\\Windows\\Web\\Screen``.
This module instead discovers whatever wallpapers the machine actually ships
with, and lets the user point at any folder of their own.
"""

from __future__ import annotations

import random
import sys
import threading
from pathlib import Path
from typing import Iterable, List, Optional, Sequence

__all__ = [
    "IMAGE_EXTENSIONS",
    "WALLPAPER_DIRS",
    "discover_images",
    "default_wallpaper_dirs",
    "default_images",
    "Playlist",
    "NoImagesFound",
]

#: Extensions every supported desktop can display.
IMAGE_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp", ".tif", ".tiff"})

#: Per-platform locations that usually hold the stock wallpapers.
WALLPAPER_DIRS = {
    "win32": [
        r"C:\Windows\Web\Wallpaper",
        r"C:\Windows\Web\4K\Wallpaper",
        r"C:\Windows\Web\Screen",
    ],
    "darwin": [
        "/System/Library/Desktop Pictures",
        "/Library/Desktop Pictures",
    ],
    "linux": [
        "/usr/share/backgrounds",
        "/usr/share/wallpapers",
        "/usr/share/pixmaps/backgrounds",
    ],
}


class NoImagesFound(RuntimeError):
    """Raised when a folder (or the whole system) yields no usable images."""


def _platform_key(platform_name: Optional[str] = None) -> str:
    name = platform_name or sys.platform
    if name.startswith("win"):
        return "win32"
    if name == "darwin":
        return "darwin"
    return "linux"


def discover_images(
    folder: str | Path,
    *,
    recursive: bool = True,
    extensions: Iterable[str] = IMAGE_EXTENSIONS,
) -> List[Path]:
    """Return the image files inside ``folder``, sorted for a stable order.

    Unreadable directories are skipped rather than raising, so a scan across
    system folders cannot be derailed by one permission error.
    """
    root = Path(folder).expanduser()
    if not root.is_dir():
        return []
    suffixes = {ext.lower() if ext.startswith(".") else f".{ext.lower()}" for ext in extensions}
    pattern = "**/*" if recursive else "*"
    found: List[Path] = []
    try:
        candidates = root.glob(pattern)
        for entry in candidates:
            try:
                if entry.is_file() and entry.suffix.lower() in suffixes:
                    found.append(entry)
            except OSError:
                continue
    except OSError:
        return []
    return sorted(found)


def default_wallpaper_dirs(platform_name: Optional[str] = None) -> List[Path]:
    """Return the stock wallpaper directories that exist on this machine."""
    dirs = [Path(p) for p in WALLPAPER_DIRS[_platform_key(platform_name)]]
    dirs.append(Path.home() / "Pictures")
    return [d for d in dirs if d.is_dir()]


def default_images(platform_name: Optional[str] = None, *, limit: Optional[int] = None) -> List[Path]:
    """Collect images from every stock wallpaper directory on this machine."""
    images: List[Path] = []
    seen = set()
    for directory in default_wallpaper_dirs(platform_name):
        for image in discover_images(directory):
            key = str(image)
            if key not in seen:
                seen.add(key)
                images.append(image)
            if limit is not None and len(images) >= limit:
                return images
    return images


class Playlist:
    """A thread-safe, endlessly cycling sequence of image paths.

    ``advance()`` returns the next path and wraps around at the end.  In
    shuffle mode the order is reshuffled on every pass, so a long run never
    repeats the same visual rhythm.
    """

    def __init__(self, paths: Sequence[str | Path], *, shuffle: bool = False, rng: Optional[random.Random] = None):
        items = [Path(p) for p in paths]
        if not items:
            raise NoImagesFound("a playlist needs at least one image")
        self._original: List[Path] = items
        self._order: List[Path] = list(items)
        self._index = 0
        self._shuffle = shuffle
        self._rng = rng or random.Random()
        self._lock = threading.Lock()
        self._laps = 0
        if shuffle:
            self._rng.shuffle(self._order)

    def __len__(self) -> int:
        return len(self._original)

    @property
    def paths(self) -> List[Path]:
        """The images in their original discovery order."""
        return list(self._original)

    @property
    def shuffle(self) -> bool:
        return self._shuffle

    @shuffle.setter
    def shuffle(self, value: bool) -> None:
        with self._lock:
            self._shuffle = bool(value)
            self._order = list(self._original)
            if self._shuffle:
                self._rng.shuffle(self._order)
            self._index = 0

    @property
    def laps(self) -> int:
        """How many complete passes through the images have finished."""
        return self._laps

    def advance(self) -> Path:
        """Return the next image, wrapping (and reshuffling) at the end."""
        with self._lock:
            if self._index >= len(self._order):
                self._index = 0
                self._laps += 1
                if self._shuffle:
                    self._rng.shuffle(self._order)
            item = self._order[self._index]
            self._index += 1
            return item

    def reset(self) -> None:
        """Rewind to the start of the playlist."""
        with self._lock:
            self._index = 0
            self._laps = 0
