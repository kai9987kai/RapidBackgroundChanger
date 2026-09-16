"""Command line interface.

``python -m rapidbackgroundchanger`` opens the window; the ``run`` subcommand
cycles wallpapers headlessly, which makes the tool scriptable and lets it be
exercised on CI where no desktop exists.
"""

from __future__ import annotations

import argparse
import signal
import sys
from pathlib import Path
from typing import List, Optional, Sequence

from . import __version__
from .backends import BACKENDS, BackendUnavailable, select_backend
from .engine import SAFE_MIN_INTERVAL, CycleEngine
from .sources import NoImagesFound, Playlist, default_images, default_wallpaper_dirs, discover_images

__all__ = ["main", "build_parser", "resolve_images"]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rapidbackgroundchanger",
        description="Rapidly cycle your desktop wallpaper.",
        epilog="Run without a subcommand to open the graphical interface.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("gui", help="open the graphical interface (default)")

    run = sub.add_parser("run", help="cycle wallpapers from the terminal")
    run.add_argument(
        "-f",
        "--folder",
        action="append",
        default=[],
        metavar="DIR",
        help="folder of images to cycle (repeatable; defaults to the system wallpapers)",
    )
    speed = run.add_mutually_exclusive_group()
    speed.add_argument(
        "-i",
        "--interval",
        type=float,
        metavar="SECONDS",
        help=f"seconds between changes (default {SAFE_MIN_INTERVAL})",
    )
    speed.add_argument("--fps", type=float, metavar="N", help="changes per second")
    run.add_argument("-n", "--count", type=int, metavar="N", help="stop after N changes")
    run.add_argument("-d", "--duration", type=float, metavar="SECONDS", help="stop after SECONDS")
    run.add_argument("-s", "--shuffle", action="store_true", help="randomise the order")
    run.add_argument(
        "--no-restore",
        action="store_true",
        help="leave the last image in place instead of restoring the original wallpaper",
    )
    run.add_argument(
        "--no-recursive", action="store_true", help="do not descend into sub-folders"
    )
    run.add_argument("-b", "--backend", help="force a specific backend (see `doctor`)")
    run.add_argument(
        "--dry-run", action="store_true", help="report changes without touching the desktop"
    )
    run.add_argument("-q", "--quiet", action="store_true", help="only print the final summary")

    images = sub.add_parser("list-images", help="show the images that would be cycled")
    images.add_argument("-f", "--folder", action="append", default=[], metavar="DIR")
    images.add_argument("--no-recursive", action="store_true")

    sub.add_parser("doctor", help="report platform, backends and discovered wallpapers")
    return parser


def resolve_images(folders: Sequence[str], *, recursive: bool = True) -> List[Path]:
    """Resolve ``folders`` to a list of images, falling back to system wallpapers."""
    if not folders:
        return default_images()

    images: List[Path] = []
    seen = set()
    missing: List[str] = []
    for folder in folders:
        path = Path(folder).expanduser()
        if not path.is_dir():
            missing.append(str(path))
            continue
        for image in discover_images(path, recursive=recursive):
            key = str(image)
            if key not in seen:
                seen.add(key)
                images.append(image)
    if not images:
        if missing:
            raise NoImagesFound(f"not a folder: {', '.join(missing)}")
        raise NoImagesFound(f"no images found in {', '.join(folders)}")
    return images


def _interval_from(args: argparse.Namespace) -> float:
    if args.fps is not None:
        if args.fps <= 0:
            raise ValueError("--fps must be greater than zero")
        return 1.0 / args.fps
    if args.interval is not None:
        if args.interval < 0:
            raise ValueError("--interval must not be negative")
        return args.interval
    return SAFE_MIN_INTERVAL


def _cmd_run(args: argparse.Namespace) -> int:
    try:
        interval = _interval_from(args)
        images = resolve_images(args.folder, recursive=not args.no_recursive)
        backend = select_backend("null" if args.dry_run else args.backend)
    except (NoImagesFound, BackendUnavailable, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    playlist = Playlist(images, shuffle=args.shuffle)

    def on_frame(index: int, path: Path) -> None:
        if not args.quiet:
            print(f"[{index}] {path}", flush=True)

    engine = CycleEngine(
        backend,
        playlist,
        interval=interval,
        restore_on_stop=not args.no_restore,
        max_frames=args.count,
        max_duration=args.duration,
        on_frame=on_frame,
    )

    def handle_signal(signum, frame) -> None:  # noqa: ARG001 - signal signature
        engine.stop(wait=False)

    previous = {}
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            previous[sig] = signal.signal(sig, handle_signal)
        except (ValueError, OSError):  # not on the main thread, or unsupported
            pass

    print(
        f"backend={backend.name} images={len(playlist)} interval={interval:g}s "
        f"shuffle={'on' if args.shuffle else 'off'}"
        + ("  (press Ctrl+C to stop)" if not (args.count or args.duration) else ""),
        file=sys.stderr,
    )
    try:
        stats = engine.run_blocking()
    finally:
        for sig, handler in previous.items():
            try:
                signal.signal(sig, handler)
            except (ValueError, OSError):  # pragma: no cover - restore best effort
                pass

    print(
        f"changed {stats.frames} wallpapers in {stats.elapsed:.2f}s "
        f"({stats.fps:.1f}/s, {stats.errors} error(s))",
        file=sys.stderr,
    )
    if stats.last_error:
        print(f"last error: {stats.last_error}", file=sys.stderr)
    return 1 if stats.errors and stats.frames == 0 else 0


def _cmd_list_images(args: argparse.Namespace) -> int:
    try:
        images = resolve_images(args.folder, recursive=not args.no_recursive)
    except NoImagesFound as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    for image in images:
        print(image)
    print(f"{len(images)} image(s)", file=sys.stderr)
    return 0


def _cmd_doctor(_args: argparse.Namespace) -> int:
    import platform

    print(f"rapidbackgroundchanger {__version__}")
    print(f"python   {platform.python_version()} on {platform.platform()}")
    try:
        import tkinter  # noqa: PLC0415

        gui = f"available (Tk {tkinter.TkVersion})"
    except Exception as exc:  # pragma: no cover - depends on the machine
        gui = f"unavailable ({type(exc).__name__}) - install python3-tk to use the GUI"
    print(f"tkinter  {gui}")

    print("\nbackends:")
    for backend in BACKENDS:
        mark = "OK " if backend.available() else "-- "
        print(f"  {mark} {backend.name:<8} {backend.description}")
    active = select_backend()
    print(f"\nselected backend: {active.name}")

    print("\nwallpaper folders found:")
    dirs = default_wallpaper_dirs()
    if not dirs:
        print("  (none - pass --folder to point at your own images)")
    for directory in dirs:
        print(f"  {directory}")
    images = default_images(limit=500)
    print(f"\n{len(images)} image(s) discoverable by default")
    return 0


def _cmd_gui(_args: argparse.Namespace) -> int:
    try:
        from .gui import run_gui  # noqa: PLC0415 - tkinter is optional
    except ImportError as exc:
        print(
            "error: the graphical interface needs tkinter, which is not installed "
            f"({exc}).\n"
            "       Install it (Debian/Ubuntu: `sudo apt install python3-tk`) or use "
            "`rapidbackgroundchanger run`.",
            file=sys.stderr,
        )
        return 3
    return run_gui()


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    handlers = {
        None: _cmd_gui,
        "gui": _cmd_gui,
        "run": _cmd_run,
        "list-images": _cmd_list_images,
        "doctor": _cmd_doctor,
    }
    return handlers[args.command](args)
