from __future__ import annotations

import random
from pathlib import Path

import pytest

from rapidbackgroundchanger.sources import (
    NoImagesFound,
    Playlist,
    default_wallpaper_dirs,
    discover_images,
)


def test_discover_images_finds_images_and_skips_other_files(image_dir: Path):
    found = discover_images(image_dir)
    assert [p.name for p in found] == ["a.jpg", "b.png", "c.BMP"]


def test_discover_images_is_case_insensitive_about_extensions(image_dir: Path):
    assert any(p.suffix == ".BMP" for p in discover_images(image_dir))


def test_discover_images_recurses_by_default(image_dir: Path):
    nested = image_dir / "deep" / "deeper"
    nested.mkdir(parents=True)
    (nested / "z.jpg").write_bytes(b"x")
    assert (nested / "z.jpg") in discover_images(image_dir)
    assert (nested / "z.jpg") not in discover_images(image_dir, recursive=False)


def test_discover_images_on_missing_folder_returns_empty(tmp_path: Path):
    assert discover_images(tmp_path / "nope") == []


def test_default_wallpaper_dirs_only_returns_existing_directories():
    assert all(d.is_dir() for d in default_wallpaper_dirs())


def test_playlist_cycles_and_wraps():
    playlist = Playlist(["a", "b"])
    assert [str(playlist.advance()) for _ in range(5)] == ["a", "b", "a", "b", "a"]
    assert playlist.laps == 2


def test_playlist_rejects_an_empty_sequence():
    with pytest.raises(NoImagesFound):
        Playlist([])


def test_playlist_shuffle_covers_every_image_each_pass():
    items = [str(i) for i in range(10)]
    playlist = Playlist(items, shuffle=True, rng=random.Random(1234))
    first_pass = {str(playlist.advance()) for _ in range(10)}
    second_pass = {str(playlist.advance()) for _ in range(10)}
    assert first_pass == second_pass == set(items)


def test_playlist_shuffle_can_be_toggled_at_runtime():
    playlist = Playlist(["a", "b", "c"], rng=random.Random(7))
    playlist.advance()
    playlist.shuffle = True
    assert playlist.shuffle is True
    assert {str(playlist.advance()) for _ in range(3)} == {"a", "b", "c"}


def test_playlist_reset_rewinds():
    playlist = Playlist(["a", "b"])
    playlist.advance()
    playlist.reset()
    assert str(playlist.advance()) == "a"
    assert playlist.laps == 0


def test_playlist_paths_preserves_original_order_even_when_shuffled():
    playlist = Playlist(["a", "b", "c"], shuffle=True, rng=random.Random(3))
    assert [str(p) for p in playlist.paths] == ["a", "b", "c"]
