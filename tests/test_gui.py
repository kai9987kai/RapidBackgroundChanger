"""GUI tests driven through a stub tkinter (see ``conftest.fake_tk``).

They cannot prove the window looks right, but they do prove the wiring: that
the buttons reach the engine, that Stop stops the run instead of destroying
the window, and that closing restores the wallpaper.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from rapidbackgroundchanger.backends import NullBackend
from rapidbackgroundchanger.engine import EngineState


def make_app(fake_tk, image_dir: Path, **kwargs):
    backend = kwargs.pop("backend", None) or NullBackend()
    app = fake_tk.gui.RapidBackgroundChangerApp(
        fake_tk.root, backend=backend, hotkey=False, **kwargs
    )
    app.folder_var.set(str(image_dir))
    app.rate_var.set(60.0)
    return app


def wait_until(predicate, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


def test_window_builds_with_menus_and_controls(fake_tk, image_dir):
    app = make_app(fake_tk, image_dir)
    assert "Rapid Background Changer" in fake_tk.root.kwargs["title"]

    menubar = fake_tk.root.kwargs["menu"]
    cascades = [entry.get("label") for entry in menubar.entries]
    assert cascades == ["Menu", "Help"]
    run_menu = next(e["menu"] for e in menubar.entries if e.get("label") == "Menu")
    assert [e.get("label") for e in run_menu.entries if "label" in e] == [
        "Start",
        "Pause / Resume",
        "Stop",
        "Exit",
    ]

    assert app.start_button is not None and app.stop_button is not None
    assert app.status_var.get().startswith("Ready")
    assert "WM_DELETE_WINDOW" in fake_tk.root.protocols
    assert "<Escape>" in fake_tk.root.bindings
    app.on_close()


def test_start_runs_the_engine_and_stop_stops_it(fake_tk, image_dir):
    app = make_app(fake_tk, image_dir)
    app.on_start()
    assert app.engine is not None and app.engine.is_running
    assert wait_until(lambda: app.engine.stats.frames >= 1)

    app.on_stop()
    assert wait_until(lambda: not app.engine.is_running)
    # Regression: the old Stop button called window.destroy().
    assert not fake_tk.root.destroyed
    app.on_close()


def test_stop_restores_the_original_wallpaper(fake_tk, image_dir):
    backend = NullBackend()
    backend.set("/user-choice.jpg")
    app = make_app(fake_tk, image_dir, backend=backend)
    app.on_start()
    assert wait_until(lambda: app.engine.stats.frames >= 2)
    app.on_stop()
    assert wait_until(lambda: not app.engine.is_running)
    assert wait_until(lambda: backend.get() == "/user-choice.jpg")
    app.on_close()


def test_escape_binding_stops_the_run(fake_tk, image_dir):
    app = make_app(fake_tk, image_dir)
    app.on_start()
    assert wait_until(lambda: app.engine.stats.frames >= 1)
    fake_tk.root.bindings["<Escape>"](object())
    assert wait_until(lambda: not app.engine.is_running)
    app.on_close()


def test_pause_button_toggles_label_and_state(fake_tk, image_dir):
    app = make_app(fake_tk, image_dir)
    app.on_start()
    app.on_pause()
    assert app.engine.state == EngineState.PAUSED
    assert app.pause_button.cget("text") == "Resume"
    app.on_pause()
    assert app.engine.state == EngineState.RUNNING
    assert app.pause_button.cget("text") == "Pause"
    app.on_close()


def test_start_is_ignored_while_already_running(fake_tk, image_dir):
    app = make_app(fake_tk, image_dir)
    app.on_start()
    first = app.engine
    app.on_start()
    assert app.engine is first
    app.on_close()


def test_speed_slider_updates_a_running_engine(fake_tk, image_dir):
    app = make_app(fake_tk, image_dir)
    app.on_start()
    app.rate_var.set(4.0)
    app.on_speed_changed()
    assert app.engine.interval == pytest.approx(0.25)
    assert "4 changes/sec" in app.speed_var.get()
    app.on_close()


def test_shuffle_checkbox_reaches_a_running_playlist(fake_tk, image_dir):
    app = make_app(fake_tk, image_dir)
    app.on_start()
    app.shuffle_var.set(True)
    app.on_shuffle_changed()
    assert app.engine.playlist.shuffle is True
    app.on_close()


def test_start_on_an_empty_folder_shows_an_error_and_does_not_run(fake_tk, tmp_path, image_dir):
    app = make_app(fake_tk, image_dir)
    empty = tmp_path / "empty"
    empty.mkdir()
    app.folder_var.set(str(empty))
    app.on_start()
    assert app.engine is None
    assert fake_tk.messagebox.calls and fake_tk.messagebox.calls[-1][0] == "error"
    app.on_close()


def test_browse_sets_the_folder(fake_tk, image_dir, tmp_path):
    app = make_app(fake_tk, image_dir)
    fake_tk.filedialog.result = str(tmp_path)
    app.on_browse()
    assert app.folder_var.get() == str(tmp_path)

    fake_tk.filedialog.result = ""  # cancelled dialog leaves the value alone
    app.on_browse()
    assert app.folder_var.get() == str(tmp_path)
    app.on_close()


def test_tick_reports_progress_then_the_final_summary(fake_tk, image_dir):
    app = make_app(fake_tk, image_dir)
    app.on_start()
    assert wait_until(lambda: app.engine.stats.frames >= 2)
    app._tick()
    assert "Running" in app.status_var.get()

    app.on_stop()
    assert wait_until(lambda: app.engine.state == EngineState.IDLE)
    app._tick()
    assert "Stopped after" in app.status_var.get()
    app.on_close()


def test_tick_reschedules_itself(fake_tk, image_dir):
    app = make_app(fake_tk, image_dir)
    before = len(fake_tk.root.after_calls)
    app._tick()
    assert len(fake_tk.root.after_calls) == before + 1
    app.on_close()


def test_close_stops_the_engine_and_destroys_the_window(fake_tk, image_dir):
    app = make_app(fake_tk, image_dir)
    app.on_start()
    assert wait_until(lambda: app.engine.stats.frames >= 1)
    app.on_close()
    assert not app.engine.is_running
    assert fake_tk.root.destroyed


def test_help_menu_actions(fake_tk, image_dir, monkeypatch):
    app = make_app(fake_tk, image_dir)
    opened = []
    monkeypatch.setattr(fake_tk.gui.webbrowser, "open_new", opened.append)

    app.on_open_github()
    assert opened == [fake_tk.gui.PROJECT_URL]

    app.on_contact()
    app.on_about()
    kinds = [call[1] for call in fake_tk.messagebox.calls]
    assert "Contact" in kinds and "About" in kinds
    app.on_close()


def test_missing_favicon_does_not_stop_the_window_opening(fake_tk, monkeypatch):
    """run_gui() must survive a missing icon; the old script printed 'rip favicon'."""
    monkeypatch.setattr(fake_tk.gui, "RapidBackgroundChangerApp", lambda root, **kw: None)
    assert fake_tk.gui.run_gui() == 0


def test_status_line_does_not_grow_while_stopping(fake_tk, image_dir):
    """Regression: _tick() used to append to its own previous status text."""

    class BrokenBackend(NullBackend):
        def set(self, path, *, persist=True):
            raise OSError("nope")

    app = make_app(fake_tk, image_dir, backend=BrokenBackend())
    app.on_start()
    assert wait_until(lambda: app.engine.stats.errors >= 2)
    app._tick()
    first = len(app.status_var.get())
    for _ in range(10):
        app._tick()
    assert len(app.status_var.get()) <= first + 4  # only the error count moves
    app.on_close()


def test_hotkey_stop_is_handed_to_the_tk_thread(fake_tk, image_dir):
    """The `keyboard` listener thread must not touch Tk variables directly."""
    app = make_app(fake_tk, image_dir)
    app.on_start()
    assert wait_until(lambda: app.engine.stats.frames >= 1)

    app._stop_requested.set()  # what the hotkey callback does, off-thread
    assert app.engine.is_running
    app._tick()  # ...and _tick(), on the Tk thread, acts on it
    assert wait_until(lambda: not app.engine.is_running)
    assert not app._stop_requested.is_set()
    app.on_close()


def test_hotkey_callback_only_sets_a_flag(fake_tk, image_dir, monkeypatch):
    import types as _types

    registered = {}
    fake_keyboard = _types.ModuleType("keyboard")

    def add_hotkey(combo, func):
        registered[combo] = func
        return f"handle:{combo}"

    fake_keyboard.add_hotkey = add_hotkey
    fake_keyboard.remove_hotkey = lambda handle: registered.clear()
    monkeypatch.setitem(__import__("sys").modules, "keyboard", fake_keyboard)

    app = fake_tk.gui.RapidBackgroundChangerApp(fake_tk.root, backend=NullBackend(), hotkey=True)
    assert "ctrl+c" in registered

    registered["ctrl+c"]()  # fire it as the listener thread would
    assert app._stop_requested.is_set()
    app.on_close()


def test_max_speed_removes_the_delay_entirely(fake_tk, image_dir):
    """The window must be able to run flat out, as the original script did."""
    app = make_app(fake_tk, image_dir)
    assert app.interval > 0

    app.maxspeed_var.set(True)
    app.on_maxspeed_changed()
    assert app.interval == 0.0
    assert app.speed_var.get() == "as fast as possible"
    assert app.speed_scale.cget("state") == "disabled"

    app.on_start()
    assert wait_until(lambda: app.engine.stats.frames >= 200, timeout=5.0)
    assert app.engine.interval == 0.0
    app.on_close()


def test_max_speed_can_be_switched_off_again(fake_tk, image_dir):
    app = make_app(fake_tk, image_dir)
    app.maxspeed_var.set(True)
    app.on_maxspeed_changed()
    app.maxspeed_var.set(False)
    app.on_maxspeed_changed()
    assert app.interval == pytest.approx(1 / 60)
    assert app.speed_scale.cget("state") == "normal"
    assert "60 changes/sec" in app.speed_var.get()
    app.on_close()


def test_max_speed_reaches_a_running_engine(fake_tk, image_dir):
    app = make_app(fake_tk, image_dir)
    app.rate_var.set(2.0)
    app.on_speed_changed()
    app.on_start()
    assert app.engine.interval == pytest.approx(0.5)

    app.maxspeed_var.set(True)
    app.on_maxspeed_changed()
    assert app.engine.interval == 0.0
    app.on_close()
