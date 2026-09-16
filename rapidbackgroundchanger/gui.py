"""Tkinter interface.

All of the work happens on :class:`~rapidbackgroundchanger.engine.CycleEngine`'s
worker thread; this module only builds widgets, forwards button presses and
polls :attr:`CycleEngine.stats` from Tk's own event loop via ``after()``.  That
keeps the window responsive - the original script called ``window.update()``
from inside its wallpaper loop and froze until the loop finished.
"""

from __future__ import annotations

import threading
import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox, ttk
from typing import List, Optional

from . import __version__
from .backends import WallpaperBackend, select_backend
from .cli import resolve_images
from .engine import CycleEngine, EngineState
from .sources import NoImagesFound, Playlist, default_wallpaper_dirs

__all__ = ["RapidBackgroundChangerApp", "run_gui"]

PROJECT_URL = "https://github.com/kai9987kai/RapidBackgroundChanger"
CONTACT_TEXT = "Email-One: kai9987kai@gmail.com\nEmail-Two: kai.piper@aol.co.uk"
SAFETY_NOTE = (
    "Rapidly changing images can flash. If you are sensitive to flashing "
    "light, keep the speed low."
)
#: How often the window refreshes its status line, in milliseconds.
POLL_INTERVAL_MS = 150
MIN_RATE = 1.0
MAX_RATE = 60.0
DEFAULT_RATE = 10.0


class RapidBackgroundChangerApp:
    """The main window.  ``root`` is injected so the class stays testable."""

    def __init__(
        self,
        root: "tk.Misc",
        *,
        backend: Optional[WallpaperBackend] = None,
        hotkey: bool = True,
    ) -> None:
        self.root = root
        self.backend = backend or select_backend()
        self.engine: Optional[CycleEngine] = None
        self._hotkey_handle = None
        self._tick_id = None
        self._want_hotkey = hotkey
        # Set from the `keyboard` listener thread; drained on the Tk thread by
        # _tick(), because Tk widgets and variables are not thread-safe.
        self._stop_requested = threading.Event()

        self.folder_var = tk.StringVar(value=self._initial_folder())
        self.rate_var = tk.DoubleVar(value=DEFAULT_RATE)
        self.shuffle_var = tk.BooleanVar(value=False)
        self.maxspeed_var = tk.BooleanVar(value=False)
        self.restore_var = tk.BooleanVar(value=True)
        self.status_var = tk.StringVar(value=f"Ready - backend: {self.backend.name}")
        self.speed_var = tk.StringVar(value=self._speed_label(DEFAULT_RATE))

        self._build_menu()
        self._build_widgets()
        self._bind_keys()
        self._install_hotkey()
        self._schedule_tick()

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------
    @staticmethod
    def _initial_folder() -> str:
        dirs: List = default_wallpaper_dirs()
        return str(dirs[0]) if dirs else ""

    def _speed_label(self, rate: float) -> str:
        if self.maxspeed_var.get():
            return "as fast as possible"
        return f"{rate:.0f} changes/sec"

    def _build_menu(self) -> None:
        menubar = tk.Menu(self.root)
        run_menu = tk.Menu(menubar, tearoff=0)
        run_menu.add_command(label="Start", command=self.on_start)
        run_menu.add_command(label="Pause / Resume", command=self.on_pause)
        run_menu.add_command(label="Stop", command=self.on_stop)
        run_menu.add_separator()
        run_menu.add_command(label="Exit", command=self.on_close)
        menubar.add_cascade(label="Menu", menu=run_menu)

        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="Contact", command=self.on_contact)
        help_menu.add_command(label="GitHub Page", command=self.on_open_github)
        help_menu.add_command(label="About", command=self.on_about)
        menubar.add_cascade(label="Help", menu=help_menu)
        self.root.config(menu=menubar)

    def _build_widgets(self) -> None:
        self.root.title(f"Rapid Background Changer {__version__}")
        frame = ttk.Frame(self.root, padding=10)
        frame.grid(row=0, column=0, sticky="nsew")
        self.root.columnconfigure(0, weight=1)
        frame.columnconfigure(1, weight=1)

        ttk.Label(frame, text="Images:").grid(row=0, column=0, sticky="w")
        self.folder_entry = ttk.Entry(frame, textvariable=self.folder_var, width=38)
        self.folder_entry.grid(row=0, column=1, sticky="ew", padx=6)
        ttk.Button(frame, text="Browse...", command=self.on_browse).grid(row=0, column=2)

        ttk.Label(frame, text="Speed:").grid(row=1, column=0, sticky="w", pady=(8, 0))
        self.speed_scale = ttk.Scale(
            frame,
            from_=MIN_RATE,
            to=MAX_RATE,
            variable=self.rate_var,
            command=self.on_speed_changed,
        )
        self.speed_scale.grid(row=1, column=1, sticky="ew", padx=6, pady=(8, 0))
        ttk.Label(frame, textvariable=self.speed_var, width=18).grid(
            row=1, column=2, sticky="w", pady=(8, 0)
        )
        self.maxspeed_check = ttk.Checkbutton(
            frame,
            text="Max speed (no delay between changes)",
            variable=self.maxspeed_var,
            command=self.on_maxspeed_changed,
        )
        self.maxspeed_check.grid(row=2, column=1, columnspan=2, sticky="w", pady=(4, 0))

        options = ttk.Frame(frame)
        options.grid(row=3, column=0, columnspan=3, sticky="w", pady=(8, 0))
        ttk.Checkbutton(
            options, text="Shuffle", variable=self.shuffle_var, command=self.on_shuffle_changed
        ).grid(row=0, column=0, padx=(0, 12))
        ttk.Checkbutton(
            options, text="Restore my wallpaper on stop", variable=self.restore_var
        ).grid(row=0, column=1)

        buttons = ttk.Frame(frame)
        buttons.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(10, 0))
        self.start_button = ttk.Button(buttons, text="Start", command=self.on_start)
        self.start_button.grid(row=0, column=0, padx=(0, 6))
        self.pause_button = ttk.Button(buttons, text="Pause", command=self.on_pause, state="disabled")
        self.pause_button.grid(row=0, column=1, padx=(0, 6))
        self.stop_button = ttk.Button(buttons, text="Stop", command=self.on_stop, state="disabled")
        self.stop_button.grid(row=0, column=2)

        ttk.Label(frame, textvariable=self.status_var, anchor="w").grid(
            row=5, column=0, columnspan=3, sticky="ew", pady=(10, 0)
        )
        ttk.Label(
            frame,
            text=f"Esc or Ctrl+C stops immediately.\n{SAFETY_NOTE}",
            anchor="w",
            justify="left",
            wraplength=430,
        ).grid(row=6, column=0, columnspan=3, sticky="ew", pady=(6, 0))

    def _bind_keys(self) -> None:
        self.root.bind("<Escape>", lambda _event: self.on_stop())
        self.root.bind("<Control-c>", lambda _event: self.on_stop())
        self.root.bind("<space>", lambda _event: self.on_pause())
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def _install_hotkey(self) -> None:
        """Register a system-wide emergency stop, if ``keyboard`` is installed.

        The dependency is optional: on Linux it needs root, and the in-window
        Esc binding already covers the common case.
        """
        if not self._want_hotkey:
            return
        try:
            import keyboard  # noqa: PLC0415 - optional dependency
        except Exception:
            return
        try:
            self._hotkey_handle = keyboard.add_hotkey("ctrl+c", self._stop_requested.set)
        except Exception:
            self._hotkey_handle = None

    def _remove_hotkey(self) -> None:
        if self._hotkey_handle is None:
            return
        try:
            import keyboard  # noqa: PLC0415

            keyboard.remove_hotkey(self._hotkey_handle)
        except Exception:
            pass
        finally:
            self._hotkey_handle = None

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    @property
    def interval(self) -> float:
        """Seconds between changes; ``0`` when Max speed is on."""
        if self.maxspeed_var.get():
            return 0.0
        return 1.0 / max(MIN_RATE, float(self.rate_var.get()))

    def on_speed_changed(self, _value=None) -> None:
        self.speed_var.set(self._speed_label(float(self.rate_var.get())))
        if self.engine is not None:
            self.engine.interval = self.interval

    def on_maxspeed_changed(self) -> None:
        """Toggle the uncapped mode, which the original script always used."""
        self.speed_scale.configure(
            state="disabled" if self.maxspeed_var.get() else "normal"
        )
        self.on_speed_changed()

    def on_shuffle_changed(self) -> None:
        if self.engine is not None:
            self.engine.playlist.shuffle = bool(self.shuffle_var.get())

    def on_browse(self) -> None:
        chosen = filedialog.askdirectory(title="Choose a folder of images")
        if chosen:
            self.folder_var.set(chosen)

    def on_start(self) -> None:
        if self.engine is not None and self.engine.is_running:
            return
        folder = self.folder_var.get().strip()
        try:
            images = resolve_images([folder] if folder else [])
        except NoImagesFound as exc:
            messagebox.showerror("No images", str(exc))
            return

        self.engine = CycleEngine(
            self.backend,
            Playlist(images, shuffle=bool(self.shuffle_var.get())),
            interval=self.interval,
            restore_on_stop=bool(self.restore_var.get()),
        )
        self.engine.start()
        self.status_var.set(f"Running - {len(images)} image(s)")
        self._refresh_buttons()

    def on_pause(self) -> None:
        if self.engine is None or not self.engine.is_running:
            return
        self.engine.toggle_pause()
        self._refresh_buttons()

    def on_stop(self) -> None:
        if self.engine is None:
            return
        self.engine.stop(wait=False)
        self.status_var.set("Stopping...")
        self._refresh_buttons()

    def on_contact(self) -> None:
        messagebox.showinfo("Contact", CONTACT_TEXT)

    def on_open_github(self) -> None:
        webbrowser.open_new(PROJECT_URL)

    def on_about(self) -> None:
        messagebox.showinfo(
            "About",
            f"Rapid Background Changer {__version__}\n"
            f"Backend: {self.backend.name}\n\n{SAFETY_NOTE}\n\n{PROJECT_URL}",
        )

    def on_close(self) -> None:
        """Stop cleanly, restore the wallpaper, then close the window."""
        self._cancel_tick()
        self._remove_hotkey()
        if self.engine is not None and self.engine.is_running:
            self.status_var.set("Stopping...")
            self.engine.stop(timeout=5.0)
        self.root.destroy()

    # ------------------------------------------------------------------
    # Status polling
    # ------------------------------------------------------------------
    def _schedule_tick(self) -> None:
        self._tick_id = self.root.after(POLL_INTERVAL_MS, self._tick)

    def _cancel_tick(self) -> None:
        if self._tick_id is not None:
            try:
                self.root.after_cancel(self._tick_id)
            except Exception:  # pragma: no cover - Tk is already tearing down
                pass
            self._tick_id = None

    def _tick(self) -> None:
        if self._stop_requested.is_set():
            self._stop_requested.clear()
            self.on_stop()

        if self.engine is not None:
            stats = self.engine.stats
            message = None
            if stats.state == EngineState.IDLE and stats.frames:
                message = (
                    f"Stopped after {stats.frames} change(s) in {stats.elapsed:.1f}s "
                    f"({stats.fps:.1f}/s)"
                )
            elif stats.is_active:
                name = stats.current.rsplit("/", 1)[-1].rsplit("\\", 1)[-1] if stats.current else "-"
                label = "Paused" if stats.state == EngineState.PAUSED else "Running"
                message = f"{label} - {stats.frames} change(s), {stats.fps:.1f}/s - {name}"
            if message is not None:
                # Build the line once: appending to the existing value grew it
                # without bound while the engine was stopping.
                if stats.errors:
                    message = f"{message}  [{stats.errors} error(s)]"
                self.status_var.set(message)
            self._refresh_buttons()
        self._schedule_tick()

    def _refresh_buttons(self) -> None:
        running = self.engine is not None and self.engine.is_running
        paused = self.engine is not None and self.engine.state == EngineState.PAUSED
        self.start_button.configure(state="disabled" if running else "normal")
        self.pause_button.configure(
            state="normal" if running else "disabled",
            text="Resume" if paused else "Pause",
        )
        self.stop_button.configure(state="normal" if running else "disabled")


def run_gui(backend: Optional[WallpaperBackend] = None) -> int:
    """Open the window and run until it is closed."""
    root = tk.Tk()
    root.resizable(False, False)
    try:
        root.iconbitmap("favicon.ico")
    except Exception:
        pass  # the icon is cosmetic and is missing when installed as a package
    RapidBackgroundChangerApp(root, backend=backend)
    root.mainloop()
    return 0
