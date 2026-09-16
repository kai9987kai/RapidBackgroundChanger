"""The wallpaper cycling engine.

The original script ran its loop on the Tk main thread, which froze the window,
and checked for the emergency stop only once every six frames.  ``CycleEngine``
runs on a worker thread and waits on a :class:`threading.Event`, so a stop
request is honoured immediately even at a one-frame-per-minute interval, and
the interface stays responsive throughout.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from .backends import WallpaperBackend
from .sources import Playlist

__all__ = ["CycleEngine", "CycleStats", "EngineState"]

#: Frames faster than this are uncomfortable to look at and risky for anyone
#: with photosensitive epilepsy, so the GUI refuses to go below it by default.
SAFE_MIN_INTERVAL = 0.05


class EngineState:
    """The states a :class:`CycleEngine` moves through."""

    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPING = "stopping"


@dataclass
class CycleStats:
    """An immutable snapshot of engine progress, safe to read from any thread."""

    state: str = EngineState.IDLE
    frames: int = 0
    errors: int = 0
    laps: int = 0
    elapsed: float = 0.0
    current: Optional[str] = None
    last_error: Optional[str] = None

    @property
    def fps(self) -> float:
        """Average wallpaper changes per second across the run."""
        return self.frames / self.elapsed if self.elapsed > 0 else 0.0

    @property
    def is_active(self) -> bool:
        return self.state in (EngineState.RUNNING, EngineState.PAUSED)


@dataclass
class _Counters:
    frames: int = 0
    errors: int = 0
    current: Optional[str] = None
    last_error: Optional[str] = None
    started_at: float = 0.0
    finished_at: float = 0.0


class CycleEngine:
    """Cycle a :class:`~rapidbackgroundchanger.sources.Playlist` on a worker thread.

    Args:
        backend: where wallpaper changes are sent.
        playlist: the images to cycle through.
        interval: seconds to wait between frames; ``0`` means as fast as possible.
        restore_on_stop: put the wallpaper that was in place at ``start()``
            back when the run ends.  The original script left you on whatever
            image it happened to stop on.
        max_frames: stop automatically after this many changes.
        max_duration: stop automatically after this many seconds.
        on_frame: optional callback invoked with ``(index, path)`` after each
            change.  It runs on the worker thread, so GUI code should poll
            :attr:`stats` instead of touching widgets from here.
        on_finish: optional callback invoked with the final :class:`CycleStats`.
        clock / sleeper: injectable time sources, used by the tests.
    """

    def __init__(
        self,
        backend: WallpaperBackend,
        playlist: Playlist,
        *,
        interval: float = 0.1,
        restore_on_stop: bool = True,
        max_frames: Optional[int] = None,
        max_duration: Optional[float] = None,
        on_frame: Optional[Callable[[int, Path], None]] = None,
        on_finish: Optional[Callable[[CycleStats], None]] = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if interval < 0:
            raise ValueError("interval must not be negative")
        if max_frames is not None and max_frames <= 0:
            raise ValueError("max_frames must be positive")
        if max_duration is not None and max_duration <= 0:
            raise ValueError("max_duration must be positive")

        self.backend = backend
        self.playlist = playlist
        self.restore_on_stop = restore_on_stop
        self.max_frames = max_frames
        self.max_duration = max_duration

        self._interval = float(interval)
        self._on_frame = on_frame
        self._on_finish = on_finish
        self._clock = clock

        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._resume_event = threading.Event()
        self._resume_event.set()
        self._lock = threading.Lock()
        self._state = EngineState.IDLE
        self._counters = _Counters()
        self._original_wallpaper: Optional[str] = None

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------
    @property
    def interval(self) -> float:
        with self._lock:
            return self._interval

    @interval.setter
    def interval(self, value: float) -> None:
        """Change the frame interval, including while the engine is running."""
        if value < 0:
            raise ValueError("interval must not be negative")
        with self._lock:
            self._interval = float(value)

    @property
    def state(self) -> str:
        with self._lock:
            return self._state

    @property
    def is_running(self) -> bool:
        return self.state in (EngineState.RUNNING, EngineState.PAUSED)

    @property
    def original_wallpaper(self) -> Optional[str]:
        """The wallpaper captured when the run started, if any."""
        return self._original_wallpaper

    @property
    def stats(self) -> CycleStats:
        """A consistent snapshot of the run so far."""
        with self._lock:
            counters = self._counters
            end = counters.finished_at or (self._clock() if counters.started_at else 0.0)
            elapsed = max(0.0, end - counters.started_at) if counters.started_at else 0.0
            return CycleStats(
                state=self._state,
                frames=counters.frames,
                errors=counters.errors,
                laps=self.playlist.laps,
                elapsed=elapsed,
                current=counters.current,
                last_error=counters.last_error,
            )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def start(self) -> None:
        """Start cycling on a background thread.  Ignored if already running."""
        with self._lock:
            if self._state in (EngineState.RUNNING, EngineState.PAUSED):
                return
            self._state = EngineState.RUNNING
            self._counters = _Counters(started_at=self._clock())

        self._stop_event.clear()
        self._resume_event.set()
        self.playlist.reset()
        self._original_wallpaper = self._capture_wallpaper()

        self._thread = threading.Thread(
            target=self._run, name="rapidbackgroundchanger-engine", daemon=True
        )
        self._thread.start()

    def stop(self, *, wait: bool = True, timeout: float = 10.0) -> CycleStats:
        """Ask the engine to stop and (by default) wait for the worker to exit."""
        with self._lock:
            if self._state in (EngineState.RUNNING, EngineState.PAUSED):
                self._state = EngineState.STOPPING
        self._stop_event.set()
        self._resume_event.set()  # unblock a paused worker so it can exit
        thread = self._thread
        if wait and thread is not None and thread is not threading.current_thread():
            thread.join(timeout)
        return self.stats

    def pause(self) -> None:
        """Hold the current wallpaper without ending the run."""
        with self._lock:
            if self._state != EngineState.RUNNING:
                return
            self._state = EngineState.PAUSED
        self._resume_event.clear()

    def resume(self) -> None:
        """Continue a paused run."""
        with self._lock:
            if self._state != EngineState.PAUSED:
                return
            self._state = EngineState.RUNNING
        self._resume_event.set()

    def toggle_pause(self) -> None:
        self.resume() if self.state == EngineState.PAUSED else self.pause()

    def join(self, timeout: Optional[float] = None) -> None:
        """Block until the worker thread finishes."""
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout)

    def run_blocking(self) -> CycleStats:
        """Run the cycle and block until it ends (used by the headless CLI)."""
        self.start()
        try:
            # Join in slices rather than one indefinite wait, so that Ctrl+C is
            # handled promptly on every platform.
            while self.is_running:
                self.join(0.2)
            self.join()
        except KeyboardInterrupt:
            self.stop()
        return self.stats

    # ------------------------------------------------------------------
    # Worker
    # ------------------------------------------------------------------
    def _capture_wallpaper(self) -> Optional[str]:
        if not self.restore_on_stop:
            return None
        try:
            return self.backend.get()
        except Exception:  # pragma: no cover - backend specific
            return None

    def _run(self) -> None:
        try:
            while not self._stop_event.is_set():
                if not self._resume_event.is_set():
                    # Paused: wake up regularly so a stop is still immediate.
                    self._resume_event.wait(0.1)
                    continue
                if self._reached_limit():
                    break

                path = self.playlist.advance()
                self._apply(path)

                interval = self.interval
                if interval and self._stop_event.wait(interval):
                    break
        finally:
            self._finish()

    def _reached_limit(self) -> bool:
        with self._lock:
            if self.max_frames is not None and self._counters.frames >= self.max_frames:
                return True
            if self.max_duration is not None and self._counters.started_at:
                if self._clock() - self._counters.started_at >= self.max_duration:
                    return True
        return False

    def _apply(self, path: Path) -> None:
        try:
            # persist=False keeps rapid cycling cheap; the restore step below
            # persists the wallpaper the user actually ends up with.
            self.backend.set(str(path), persist=False)
        except Exception as exc:
            with self._lock:
                self._counters.errors += 1
                self._counters.last_error = f"{type(exc).__name__}: {exc}"
            return

        with self._lock:
            self._counters.frames += 1
            self._counters.current = str(path)
            index = self._counters.frames

        if self._on_frame is not None:
            try:
                self._on_frame(index, path)
            except Exception:  # a broken callback must not kill the run
                with self._lock:
                    self._counters.errors += 1

    def _finish(self) -> None:
        self._restore()
        with self._lock:
            self._counters.finished_at = self._clock()
            self._state = EngineState.IDLE
        if self._on_finish is not None:
            try:
                self._on_finish(self.stats)
            except Exception:  # pragma: no cover - callback owns its errors
                pass

    def _restore(self) -> None:
        target = self._original_wallpaper
        if not self.restore_on_stop or not target:
            # Nothing to restore, but persist the final frame so the desktop
            # keeps it across a reboot.
            self._persist_current()
            return
        try:
            self.backend.set(target, persist=True)
        except Exception as exc:
            with self._lock:
                self._counters.errors += 1
                self._counters.last_error = f"restore failed: {exc}"

    def _persist_current(self) -> None:
        with self._lock:
            current = self._counters.current
        if not current:
            return
        try:
            self.backend.set(current, persist=True)
        except Exception:  # pragma: no cover - best effort
            pass
