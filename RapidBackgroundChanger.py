#!/usr/bin/env python3
"""Backwards-compatible entry point.

Historically this file held the whole program, so people run it directly.  It
now forwards to the :mod:`rapidbackgroundchanger` package, which works on
Windows, macOS and Linux and no longer needs ``pywin32``.

    python RapidBackgroundChanger.py                 # open the window
    python RapidBackgroundChanger.py run -n 50       # cycle from the terminal
    python RapidBackgroundChanger.py doctor          # check this machine
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rapidbackgroundchanger.cli import main  # noqa: E402 - needs the path above

if __name__ == "__main__":
    raise SystemExit(main())
