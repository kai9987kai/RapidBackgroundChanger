# Rapid Background Changer

Rapidly cycles your desktop wallpaper — now on **Windows, macOS and Linux**, with
a responsive window, a scriptable command line, and your original wallpaper put
back when you stop.

![Rapid Background Changer](https://raw.githubusercontent.com/kai9987kai/kai9987kai.github.io/master/Screenshots/cap2.PNG)

> **Photosensitivity note.** At high speeds this flashes images in quick
> succession. If you are sensitive to flashing light, keep the speed low. The
> window's speed slider starts at a gentle 10 changes per second.

## Install

No third-party packages are required. Python 3.8 or newer is enough:

```bash
git clone https://github.com/kai9987kai/RapidBackgroundChanger
cd RapidBackgroundChanger
python RapidBackgroundChanger.py
```

Or install it as a proper command:

```bash
pip install .
rapidbackgroundchanger
```

The graphical interface needs `tkinter`, which ships with Python on Windows and
macOS. On Debian/Ubuntu install it with `sudo apt install python3-tk`. The
command line works without it.

## Use it

```bash
rapidbackgroundchanger                  # open the window
rapidbackgroundchanger doctor           # what works on this machine?
rapidbackgroundchanger run              # cycle the system wallpapers
rapidbackgroundchanger run -f ~/Pictures --fps 20 -n 200 --shuffle
rapidbackgroundchanger run --dry-run    # show the changes without making them
```

`python RapidBackgroundChanger.py <args>` accepts exactly the same arguments, so
existing shortcuts keep working.

### `run` options

| Option | What it does |
| --- | --- |
| `-f, --folder DIR` | Folder of images to cycle. Repeatable. Defaults to the wallpapers your system already ships. |
| `-i, --interval S` | Seconds between changes. `0` means as fast as possible. |
| `--fps N` | Changes per second, instead of `--interval`. |
| `-n, --count N` | Stop after N changes. |
| `-d, --duration S` | Stop after S seconds. |
| `-s, --shuffle` | Randomise the order, reshuffled on every pass. |
| `--no-restore` | Keep the last image instead of restoring your wallpaper. |
| `--no-recursive` | Do not descend into sub-folders. |
| `-b, --backend NAME` | Force a backend (see `doctor`). |
| `--dry-run` | Report changes without touching the desktop. |
| `-q, --quiet` | Only print the summary. |

Stop a run at any time with `Ctrl+C`; in the window, press `Escape` (or `Ctrl+C`),
`Space` pauses and resumes.

## How it works

| Module | Responsibility |
| --- | --- |
| `backends.py` | One small class per platform: Windows (`SystemParametersInfoW` through `ctypes`), macOS (`osascript`), GNOME (`gsettings`), XFCE (`xfconf-query`), X11 (`feh`), plus a `null` backend for dry runs. |
| `sources.py` | Finds images and cycles them as a thread-safe `Playlist`. |
| `engine.py` | `CycleEngine` — runs the loop on a worker thread with pause, resume, live speed changes, limits and statistics. |
| `cli.py` | Argument parsing, the headless `run`, and `doctor`. |
| `gui.py` | Tkinter window; polls the engine from Tk's event loop so it never freezes. |

Use it as a library, too:

```python
from rapidbackgroundchanger import CycleEngine, Playlist, discover_images, select_backend

engine = CycleEngine(
    select_backend(),
    Playlist(discover_images("~/Pictures"), shuffle=True),
    interval=0.05,
    max_duration=10,
)
engine.run_blocking()   # your wallpaper is restored afterwards
```

## What changed in 2.0

The original was a single Windows-only script. This release fixes its
long-standing defects and grows the rest around them:

* **The window no longer freezes.** The cycle ran on Tk's own thread and called
  `window.update()` from inside the loop; it now runs on a worker thread.
* **Stop stops.** The old Stop button destroyed the window, and the loop's
  `running = False` only ever touched a local variable, so it never ended.
* **The emergency stop is instant.** `Ctrl+C` used to be checked once every six
  wallpapers; the worker now waits on an event and reacts immediately.
* **Your wallpaper comes back** when the run ends, instead of leaving you on
  whatever image it stopped on.
* **Any images, not six.** The old paths were hard-coded to
  `C:\Windows\Web\Screen\img10{0..5}.jpg`; point it at any folder, or let it find
  your system wallpapers.
* **No `pywin32`.** The Windows backend uses `ctypes`, and the registry handle it
  opens is now actually closed.
* **macOS and Linux support**, plus a `null` backend so it runs anywhere.
* **Rapid frames are cheap.** Each change skips the registry write and the
  system-wide broadcast; only the final wallpaper is persisted.
* **Dead code removed.** Four threads were started *after* `mainloop()` returned,
  one of them targeting a non-callable.
* **Tests and CI.** 78 tests across Windows, macOS and Linux on Python 3.8–3.12.

## Contributing

```bash
pip install -e ".[dev]"
python -m pytest
```

The test suite needs no desktop: wallpaper changes go to the `null` backend and
the GUI is driven through a stub `tkinter`, so everything runs on CI.

## Contact

kai9987kai@gmail.com · kai.piper@aol.co.uk

## Licence

GPL-3.0 — see [LICENSE](LICENSE).
