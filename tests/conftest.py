"""Shared fixtures.

``fake_tk`` installs a miniature stand-in for tkinter so the GUI can be
exercised on machines (and CI runners) without a display or python3-tk.
"""

from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture
def image_dir(tmp_path: Path) -> Path:
    """A folder with three images and one file that is not an image."""
    folder = tmp_path / "pics"
    folder.mkdir()
    for name in ("a.jpg", "b.png", "c.BMP"):
        (folder / name).write_bytes(b"not really an image")
    (folder / "notes.txt").write_text("ignore me")
    return folder


class FakeWidget:
    """Records the calls the GUI makes, and nothing else."""

    def __init__(self, master=None, **kwargs):
        self.master = master
        self.kwargs = dict(kwargs)
        self.children = []
        self.bindings = {}
        self.protocols = {}
        self.menu = None
        self.destroyed = False
        self._after_id = 0
        self.after_calls = []
        if isinstance(master, FakeWidget):
            master.children.append(self)

    # layout / configuration no-ops
    def grid(self, **kwargs):
        self.kwargs.update(kwargs)

    def pack(self, **kwargs):
        self.kwargs.update(kwargs)

    def columnconfigure(self, *args, **kwargs):
        pass

    def rowconfigure(self, *args, **kwargs):
        pass

    def configure(self, **kwargs):
        self.kwargs.update(kwargs)

    config = configure

    def cget(self, key):
        return self.kwargs.get(key)

    def title(self, value=None):
        self.kwargs["title"] = value
        return value

    def resizable(self, *args):
        pass

    def iconbitmap(self, *args):
        raise RuntimeError("no icon in tests")

    def bind(self, sequence, func):
        self.bindings[sequence] = func

    def protocol(self, name, func):
        self.protocols[name] = func

    def after(self, _ms, func=None):
        self._after_id += 1
        self.after_calls.append(func)
        return self._after_id

    def after_cancel(self, _identifier):
        pass

    def destroy(self):
        self.destroyed = True

    def mainloop(self):
        pass


class FakeMenu(FakeWidget):
    def __init__(self, master=None, **kwargs):
        super().__init__(master, **kwargs)
        self.entries = []

    def add_command(self, **kwargs):
        self.entries.append(kwargs)

    def add_separator(self):
        self.entries.append({"type": "separator"})

    def add_cascade(self, **kwargs):
        self.entries.append(kwargs)


class FakeVar:
    _cast = staticmethod(lambda value: value)

    def __init__(self, master=None, value=None):
        self._value = self._cast(value) if value is not None else self._default()

    @staticmethod
    def _default():
        return ""

    def get(self):
        return self._value

    def set(self, value):
        self._value = self._cast(value)


class FakeStringVar(FakeVar):
    _cast = staticmethod(str)


class FakeDoubleVar(FakeVar):
    _cast = staticmethod(float)

    @staticmethod
    def _default():
        return 0.0


class FakeBooleanVar(FakeVar):
    _cast = staticmethod(bool)

    @staticmethod
    def _default():
        return False


def _build_fake_tkinter():
    tk = types.ModuleType("tkinter")
    tk.Misc = FakeWidget
    tk.Tk = FakeWidget
    tk.Frame = FakeWidget
    tk.Label = FakeWidget
    tk.Menu = FakeMenu
    tk.StringVar = FakeStringVar
    tk.DoubleVar = FakeDoubleVar
    tk.BooleanVar = FakeBooleanVar
    tk.TkVersion = 8.6

    ttk = types.ModuleType("tkinter.ttk")
    for name in ("Frame", "Label", "Entry", "Button", "Scale", "Checkbutton", "Separator"):
        setattr(ttk, name, FakeWidget)

    filedialog = types.ModuleType("tkinter.filedialog")
    filedialog.calls = []
    filedialog.result = ""

    def askdirectory(**kwargs):
        filedialog.calls.append(kwargs)
        return filedialog.result

    filedialog.askdirectory = askdirectory

    messagebox = types.ModuleType("tkinter.messagebox")
    messagebox.calls = []
    messagebox.showinfo = lambda title, message: messagebox.calls.append(("info", title, message))
    messagebox.showerror = lambda title, message: messagebox.calls.append(("error", title, message))

    tk.ttk = ttk
    tk.filedialog = filedialog
    tk.messagebox = messagebox
    return tk, ttk, filedialog, messagebox


@pytest.fixture
def fake_tk(monkeypatch):
    """Import ``rapidbackgroundchanger.gui`` against a stub tkinter."""
    tk, ttk, filedialog, messagebox = _build_fake_tkinter()
    monkeypatch.setitem(sys.modules, "tkinter", tk)
    monkeypatch.setitem(sys.modules, "tkinter.ttk", ttk)
    monkeypatch.setitem(sys.modules, "tkinter.filedialog", filedialog)
    monkeypatch.setitem(sys.modules, "tkinter.messagebox", messagebox)
    monkeypatch.delitem(sys.modules, "rapidbackgroundchanger.gui", raising=False)

    gui = importlib.import_module("rapidbackgroundchanger.gui")
    gui = importlib.reload(gui)
    try:
        yield types.SimpleNamespace(
            gui=gui, tk=tk, filedialog=filedialog, messagebox=messagebox, root=tk.Tk()
        )
    finally:
        sys.modules.pop("rapidbackgroundchanger.gui", None)
