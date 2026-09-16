"""Engine tests.

Several of these are regression tests for defects in the original script:
the loop blocked its caller, the Stop button only destroyed the window, the
emergency stop was checked once every six frames, and whatever wallpaper the
loop happened to stop on was left in place.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from rapidbackgroundchanger.backends import NullBackend
from rapidbackgroundchanger.engine import CycleEngine, EngineState
from rapidbackgroundchanger.sources import Playlist

PATHS = ["/one.jpg", "/two.jpg", "/three.jpg"]
#: The engine reports paths as Playlist stores them, so expectations must be
#: normalised the same way -- on Windows "/one.jpg" becomes "\one.jpg".
EXPECTED = [str(Path(p)) for p in PATHS]


class FlakyBackend(NullBackend):
    """Fails every ``fail_every``-th call, to exercise error handling."""

    def __init__(self, fail_every: int = 2):
        super().__init__()
        self.fail_every = fail_every
        self.attempts = 0

    def set(self, path: str, *, persist: bool = True) -> None:
        self.attempts += 1
        if self.attempts % self.fail_every == 0:
            raise OSError("desktop said no")
        super().set(path, persist=persist)


def make_engine(**kwargs) -> CycleEngine:
    kwargs.setdefault("interval", 0)
    return CycleEngine(NullBackend(), Playlist(PATHS), **kwargs)


def wait_until(predicate, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


def test_runs_exactly_max_frames():
    engine = make_engine(max_frames=7, restore_on_stop=False)
    stats = engine.run_blocking()
    assert stats.frames == 7
    assert stats.state == EngineState.IDLE
    assert stats.errors == 0


def test_max_duration_stops_the_run():
    engine = make_engine(interval=0.01, max_duration=0.1, restore_on_stop=False)
    stats = engine.run_blocking()
    assert 0.05 <= stats.elapsed < 2.0
    assert stats.frames > 0


def test_start_does_not_block_the_caller():
    """The original looped on the caller's thread and froze the GUI."""
    engine = make_engine(interval=0.01)
    began = time.monotonic()
    engine.start()
    assert time.monotonic() - began < 1.0
    assert engine.is_running
    engine.stop()


def test_stop_is_immediate_even_with_a_long_interval():
    """Regression: the old emergency stop was only checked every six frames."""
    engine = make_engine(interval=30.0)
    engine.start()
    assert wait_until(lambda: engine.stats.frames >= 1)

    began = time.monotonic()
    engine.stop()
    assert time.monotonic() - began < 2.0
    assert not engine.is_running


def test_stop_restores_the_wallpaper_that_was_there_first():
    backend = NullBackend()
    backend.set("/my-own-wallpaper.jpg")
    engine = CycleEngine(backend, Playlist(PATHS), interval=0, max_frames=5)
    engine.run_blocking()
    assert engine.original_wallpaper == "/my-own-wallpaper.jpg"
    assert backend.get() == "/my-own-wallpaper.jpg"
    assert backend.history[-1] == "/my-own-wallpaper.jpg"


def test_no_restore_leaves_the_last_image_in_place():
    backend = NullBackend()
    backend.set("/my-own-wallpaper.jpg")
    engine = CycleEngine(
        backend, Playlist(PATHS), interval=0, max_frames=4, restore_on_stop=False
    )
    engine.run_blocking()
    assert backend.get() == EXPECTED[3 % len(EXPECTED)]


def test_restore_persists_to_disk_even_though_frames_do_not():
    """Rapid frames skip the expensive persist; the final wallpaper must not."""
    persisted = []

    class RecordingBackend(NullBackend):
        def set(self, path, *, persist=True):
            persisted.append((path, persist))
            super().set(path, persist=persist)

    backend = RecordingBackend()
    backend.set("/original.jpg")
    persisted.clear()
    CycleEngine(backend, Playlist(PATHS), interval=0, max_frames=3).run_blocking()

    assert [p for _, p in persisted[:3]] == [False, False, False]
    assert persisted[-1] == ("/original.jpg", True)


def test_pause_holds_the_wallpaper_then_resume_continues():
    engine = make_engine(interval=0.01, restore_on_stop=False)
    engine.start()
    assert wait_until(lambda: engine.stats.frames >= 1)

    engine.pause()
    assert engine.state == EngineState.PAUSED
    time.sleep(0.15)
    frozen = engine.stats.frames
    time.sleep(0.15)
    assert engine.stats.frames == frozen

    engine.resume()
    assert wait_until(lambda: engine.stats.frames > frozen)
    engine.stop()


def test_stop_releases_a_paused_engine():
    engine = make_engine(interval=0.01)
    engine.start()
    assert wait_until(lambda: engine.stats.frames >= 1)
    engine.pause()
    engine.stop(timeout=3.0)
    assert not engine.is_running
    assert engine.state == EngineState.IDLE


def test_toggle_pause_flips_both_ways():
    engine = make_engine(interval=0.01)
    engine.start()
    engine.toggle_pause()
    assert engine.state == EngineState.PAUSED
    engine.toggle_pause()
    assert engine.state == EngineState.RUNNING
    engine.stop()


def test_backend_errors_are_counted_and_do_not_end_the_run():
    backend = FlakyBackend(fail_every=2)
    engine = CycleEngine(
        backend, Playlist(PATHS), interval=0, max_frames=5, restore_on_stop=False
    )
    stats = engine.run_blocking()
    assert stats.frames == 5
    assert stats.errors >= 4
    assert "desktop said no" in (stats.last_error or "")


def test_a_broken_callback_cannot_kill_the_run():
    def explode(index, path):
        raise ValueError("callback bug")

    engine = CycleEngine(
        NullBackend(),
        Playlist(PATHS),
        interval=0,
        max_frames=3,
        restore_on_stop=False,
        on_frame=explode,
    )
    stats = engine.run_blocking()
    assert stats.frames == 3
    assert stats.errors == 3


def test_on_frame_and_on_finish_callbacks_fire():
    seen = []
    finished = []
    engine = CycleEngine(
        NullBackend(),
        Playlist(PATHS),
        interval=0,
        max_frames=3,
        restore_on_stop=False,
        on_frame=lambda index, path: seen.append((index, str(path))),
        on_finish=finished.append,
    )
    engine.run_blocking()
    assert [index for index, _ in seen] == [1, 2, 3]
    assert [path for _, path in seen] == EXPECTED
    assert finished and finished[0].frames == 3


def test_interval_can_change_while_running():
    engine = make_engine(interval=5.0)
    engine.start()
    engine.interval = 0.01
    assert engine.interval == 0.01
    engine.stop()


def test_calling_start_twice_does_not_spawn_a_second_worker():
    engine = make_engine(interval=0.05)
    before = threading.active_count()
    engine.start()
    engine.start()
    assert threading.active_count() <= before + 1
    engine.stop()


def test_stop_before_start_is_harmless():
    engine = make_engine()
    assert engine.stop().frames == 0


def test_stats_report_a_sane_rate():
    engine = make_engine(interval=0.01, max_frames=5, restore_on_stop=False)
    stats = engine.run_blocking()
    assert stats.fps > 0
    assert stats.elapsed > 0
    assert stats.current in EXPECTED


def test_invalid_configuration_is_rejected():
    with pytest.raises(ValueError):
        CycleEngine(NullBackend(), Playlist(PATHS), interval=-1)
    with pytest.raises(ValueError):
        CycleEngine(NullBackend(), Playlist(PATHS), max_frames=0)
    with pytest.raises(ValueError):
        CycleEngine(NullBackend(), Playlist(PATHS), max_duration=0)
    with pytest.raises(ValueError):
        make_engine().interval = -0.5


def test_worker_thread_is_a_daemon_so_it_never_hangs_exit():
    engine = make_engine(interval=1.0)
    engine.start()
    assert engine._thread is not None and engine._thread.daemon
    engine.stop()
