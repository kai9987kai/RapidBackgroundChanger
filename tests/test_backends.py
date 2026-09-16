from __future__ import annotations

import pytest

from rapidbackgroundchanger import backends
from rapidbackgroundchanger.backends import (
    BackendUnavailable,
    GnomeBackend,
    NullBackend,
    WindowsBackend,
    available_backends,
    select_backend,
)


def test_null_backend_records_history_without_touching_the_desktop():
    backend = NullBackend()
    backend.set("/one.jpg")
    backend.set("/two.jpg", persist=False)
    assert backend.history == ["/one.jpg", "/two.jpg"]
    assert backend.get() == "/two.jpg"


def test_null_backend_is_always_available():
    assert NullBackend.available() is True
    assert NullBackend in available_backends()


def test_select_backend_by_name():
    assert select_backend("null").name == "null"


def test_select_backend_rejects_unknown_names():
    with pytest.raises(BackendUnavailable, match="unknown backend"):
        select_backend("does-not-exist")


def test_select_backend_rejects_a_known_but_unavailable_backend(monkeypatch):
    monkeypatch.setattr(WindowsBackend, "available", classmethod(lambda cls: False))
    with pytest.raises(BackendUnavailable, match="not available"):
        select_backend("windows")


def test_select_backend_auto_detects_and_always_returns_something():
    assert select_backend().name in {b.name for b in backends.BACKENDS}


def test_select_backend_prefers_the_first_available_entry(monkeypatch):
    """The earliest available entry in BACKENDS wins, whatever the host is.

    Without pinning every entry this passes on Linux and fails on a real Mac
    or PC, where MacOSBackend and WindowsBackend genuinely come first.
    """
    for backend in backends.BACKENDS:
        monkeypatch.setattr(backend, "available", classmethod(lambda cls: False))
    monkeypatch.setattr(GnomeBackend, "available", classmethod(lambda cls: True))
    monkeypatch.setattr(NullBackend, "available", classmethod(lambda cls: True))

    selected = select_backend()
    assert isinstance(selected, GnomeBackend)  # Gnome precedes Null in BACKENDS
    assert selected.name == "gnome"


def test_windows_backend_refuses_to_construct_off_windows(monkeypatch):
    monkeypatch.setattr(WindowsBackend, "available", classmethod(lambda cls: False))
    with pytest.raises(BackendUnavailable):
        WindowsBackend()


def test_every_backend_declares_a_name_and_description():
    for backend in backends.BACKENDS:
        assert backend.name and backend.name != "abstract"
        assert backend.description


def test_gnome_backend_sets_both_light_and_dark_uris(monkeypatch, tmp_path):
    image = tmp_path / "w.jpg"
    image.write_bytes(b"x")
    calls = []

    def fake_run(self, argv, capture=False):
        calls.append(list(argv))
        if "picture-uri-dark" in argv:
            raise OSError("old gnome")
        return None

    monkeypatch.setattr(GnomeBackend, "_run", fake_run)
    backend = GnomeBackend.__new__(GnomeBackend)
    backend._last_set = None
    backend.set(str(image))

    assert calls[0][:4] == ["gsettings", "set", "org.gnome.desktop.background", "picture-uri"]
    assert calls[0][4].startswith("file://")
    # A missing picture-uri-dark key on older GNOME must not fail the change.
    assert any("picture-uri-dark" in call for call in calls)
    assert backend.get() == str(image)


def test_gnome_backend_get_decodes_a_file_uri(monkeypatch):
    monkeypatch.setattr(
        GnomeBackend, "_run", lambda self, argv, capture=False: "'file:///tmp/a%20b.jpg'"
    )
    backend = GnomeBackend.__new__(GnomeBackend)
    backend._last_set = None
    assert backend.get() == "/tmp/a b.jpg"
