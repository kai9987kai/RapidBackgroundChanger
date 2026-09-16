"""Desktop wallpaper backends.

Each backend knows how to read and write the desktop wallpaper for one
platform.  Backends are deliberately tiny and dependency free: the Windows
implementation talks to ``user32`` through :mod:`ctypes`, so ``pywin32`` is no
longer required, and every other platform shells out to the tool its desktop
environment already ships.

``NullBackend`` implements the same interface without touching the desktop,
which is what ``--dry-run`` and the test-suite use.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Optional, Sequence, Type

__all__ = [
    "WallpaperBackend",
    "NullBackend",
    "WindowsBackend",
    "MacOSBackend",
    "GnomeBackend",
    "XfceBackend",
    "FehBackend",
    "BACKENDS",
    "available_backends",
    "select_backend",
    "BackendUnavailable",
]


class BackendUnavailable(RuntimeError):
    """Raised when a backend is requested but cannot run on this machine."""


class WallpaperBackend(ABC):
    """Common interface implemented by every wallpaper backend."""

    #: Short identifier used by ``--backend`` and shown by ``doctor``.
    name: str = "abstract"
    #: Human readable description, shown by ``doctor``.
    description: str = ""

    def __init__(self) -> None:
        self._last_set: Optional[str] = None

    @classmethod
    def available(cls) -> bool:
        """Return ``True`` when this backend can drive the current desktop."""
        return False

    @abstractmethod
    def set(self, path: str, *, persist: bool = True) -> None:
        """Make ``path`` the desktop wallpaper.

        ``persist`` asks the backend to write the change through to whatever
        permanent store the desktop keeps.  Rapid cycling passes
        ``persist=False`` so that hundreds of frames a second do not each
        trigger a disk write; the final frame is always persisted.
        """

    def get(self) -> Optional[str]:
        """Return the current wallpaper path, or ``None`` if unknown."""
        return self._last_set

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<{type(self).__name__} name={self.name!r}>"


class NullBackend(WallpaperBackend):
    """A backend that records calls instead of touching the desktop."""

    name = "null"
    description = "Dry run: records changes without touching the desktop"

    def __init__(self) -> None:
        super().__init__()
        self.history: List[str] = []

    @classmethod
    def available(cls) -> bool:
        return True

    def set(self, path: str, *, persist: bool = True) -> None:
        self.history.append(path)
        self._last_set = path


class WindowsBackend(WallpaperBackend):
    """Windows backend built on ``SystemParametersInfoW`` via :mod:`ctypes`."""

    name = "windows"
    description = "Windows SystemParametersInfoW (no pywin32 required)"

    SPI_SETDESKWALLPAPER = 20
    SPI_GETDESKWALLPAPER = 115
    SPIF_UPDATEINIFILE = 0x01
    SPIF_SENDWININICHANGE = 0x02
    MAX_PATH = 260

    @classmethod
    def available(cls) -> bool:
        return sys.platform == "win32"

    def __init__(self) -> None:
        super().__init__()
        if not self.available():
            raise BackendUnavailable("the Windows backend only runs on Windows")
        import ctypes  # noqa: PLC0415 - imported lazily; Windows only

        # use_last_error=True makes ctypes capture the real GetLastError value
        # for the failing call, rather than whatever ran most recently.
        self._user32 = ctypes.WinDLL("user32", use_last_error=True)
        self._ctypes = ctypes

    def set(self, path: str, *, persist: bool = True) -> None:
        flags = (self.SPIF_UPDATEINIFILE | self.SPIF_SENDWININICHANGE) if persist else 0
        ok = self._user32.SystemParametersInfoW(
            self.SPI_SETDESKWALLPAPER, 0, str(path), flags
        )
        if not ok:
            raise OSError(
                f"SystemParametersInfoW failed for {path!r} "
                f"(error {self._ctypes.get_last_error()})"
            )
        self._last_set = str(path)

    def get(self) -> Optional[str]:
        buf = self._ctypes.create_unicode_buffer(self.MAX_PATH)
        ok = self._user32.SystemParametersInfoW(
            self.SPI_GETDESKWALLPAPER, self.MAX_PATH, buf, 0
        )
        if not ok:
            return self._last_set
        return buf.value or self._last_set

    def set_style(self, style: str = "10", tile: bool = False) -> None:
        """Set the ``WallpaperStyle``/``TileWallpaper`` registry values.

        ``style`` follows Windows' own numbering (``0`` centre, ``2`` stretch,
        ``6`` fit, ``10`` fill).  The registry handle is always closed, which
        the original script forgot to do.
        """
        import winreg  # noqa: PLC0415 - Windows only

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, r"Control Panel\Desktop", 0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.SetValueEx(key, "WallpaperStyle", 0, winreg.REG_SZ, str(style))
            winreg.SetValueEx(key, "TileWallpaper", 0, winreg.REG_SZ, "1" if tile else "0")


class _SubprocessBackend(WallpaperBackend):
    """Shared helper for backends that shell out to a desktop tool."""

    def _run(self, argv: Sequence[str], *, capture: bool = False) -> Optional[str]:
        try:
            result = subprocess.run(
                list(argv),
                check=True,
                capture_output=True,
                text=True,
                timeout=10,
            )
        except (subprocess.SubprocessError, OSError) as exc:
            raise OSError(f"{argv[0]} failed: {exc}") from exc
        return result.stdout.strip() if capture else None


class MacOSBackend(_SubprocessBackend):
    """macOS backend driving System Events through ``osascript``."""

    name = "macos"
    description = "macOS osascript / System Events"

    @classmethod
    def available(cls) -> bool:
        return sys.platform == "darwin" and shutil.which("osascript") is not None

    def set(self, path: str, *, persist: bool = True) -> None:
        script = (
            'tell application "System Events" to tell every desktop '
            f'to set picture to POSIX file "{path}"'
        )
        self._run(["osascript", "-e", script])
        self._last_set = str(path)


class GnomeBackend(_SubprocessBackend):
    """GNOME/Cinnamon/Unity backend using ``gsettings``."""

    name = "gnome"
    description = "GNOME-family desktops via gsettings"
    _SCHEMA = "org.gnome.desktop.background"

    @classmethod
    def available(cls) -> bool:
        if sys.platform.startswith("win") or sys.platform == "darwin":
            return False
        if shutil.which("gsettings") is None:
            return False
        desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()
        return any(name in desktop for name in ("gnome", "unity", "cinnamon", "budgie"))

    def set(self, path: str, *, persist: bool = True) -> None:
        uri = Path(path).absolute().as_uri()
        self._run(["gsettings", "set", self._SCHEMA, "picture-uri", uri])
        # Ignore failures on the dark variant: it only exists on newer GNOME.
        try:
            self._run(["gsettings", "set", self._SCHEMA, "picture-uri-dark", uri])
        except OSError:
            pass
        self._last_set = str(path)

    def get(self) -> Optional[str]:
        try:
            value = self._run(["gsettings", "get", self._SCHEMA, "picture-uri"], capture=True)
        except OSError:
            return self._last_set
        if not value:
            return self._last_set
        value = value.strip().strip("'\"")
        if value.startswith("file://"):
            from urllib.parse import unquote, urlparse  # noqa: PLC0415

            return unquote(urlparse(value).path)
        return value or self._last_set


class XfceBackend(_SubprocessBackend):
    """XFCE backend using ``xfconf-query``."""

    name = "xfce"
    description = "XFCE via xfconf-query"

    @classmethod
    def available(cls) -> bool:
        if sys.platform.startswith("win") or sys.platform == "darwin":
            return False
        if shutil.which("xfconf-query") is None:
            return False
        return "xfce" in os.environ.get("XDG_CURRENT_DESKTOP", "").lower()

    def _properties(self) -> List[str]:
        try:
            listing = self._run(["xfconf-query", "-c", "xfce4-desktop", "-l"], capture=True) or ""
        except OSError:
            return []
        return [line.strip() for line in listing.splitlines() if line.strip().endswith("last-image")]

    def set(self, path: str, *, persist: bool = True) -> None:
        targets = self._properties()
        if not targets:
            raise OSError("no xfce4-desktop last-image properties found")
        for prop in targets:
            self._run(["xfconf-query", "-c", "xfce4-desktop", "-p", prop, "-s", str(path)])
        self._last_set = str(path)


class FehBackend(_SubprocessBackend):
    """Last-resort X11 backend using ``feh``, for tiling window managers."""

    name = "feh"
    description = "X11 fallback via feh --bg-fill"

    @classmethod
    def available(cls) -> bool:
        if sys.platform.startswith("win") or sys.platform == "darwin":
            return False
        return shutil.which("feh") is not None and bool(os.environ.get("DISPLAY"))

    def set(self, path: str, *, persist: bool = True) -> None:
        self._run(["feh", "--no-fehbg", "--bg-fill", str(path)])
        self._last_set = str(path)


#: Ordered by preference; the first available backend wins.
BACKENDS: List[Type[WallpaperBackend]] = [
    WindowsBackend,
    MacOSBackend,
    GnomeBackend,
    XfceBackend,
    FehBackend,
    NullBackend,
]


def available_backends() -> List[Type[WallpaperBackend]]:
    """Return every backend class that reports itself usable here."""
    return [backend for backend in BACKENDS if backend.available()]


def select_backend(name: Optional[str] = None) -> WallpaperBackend:
    """Instantiate a backend by ``name``, or auto-detect the best one.

    Auto-detection never raises: it falls back to :class:`NullBackend` so the
    application still starts (and says so) on an unsupported desktop.
    """
    if name:
        for backend in BACKENDS:
            if backend.name == name:
                if not backend.available():
                    raise BackendUnavailable(
                        f"backend {name!r} is not available on this system "
                        f"({platform.system()})"
                    )
                return backend()
        known = ", ".join(backend.name for backend in BACKENDS)
        raise BackendUnavailable(f"unknown backend {name!r}; known backends: {known}")

    for backend in BACKENDS:
        if backend.available():
            return backend()
    return NullBackend()  # pragma: no cover - NullBackend is always available
