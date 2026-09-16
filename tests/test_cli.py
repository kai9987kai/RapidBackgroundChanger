from __future__ import annotations

from pathlib import Path

import pytest

from rapidbackgroundchanger import __version__
from rapidbackgroundchanger.cli import build_parser, main, resolve_images
from rapidbackgroundchanger.sources import NoImagesFound


def test_version_flag(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_doctor_reports_backends_and_gui_state(capsys):
    assert main(["doctor"]) == 0
    out = capsys.readouterr().out
    assert "backends:" in out
    assert "selected backend:" in out
    assert "tkinter" in out


def test_list_images_prints_each_image(image_dir: Path, capsys):
    assert main(["list-images", "--folder", str(image_dir)]) == 0
    captured = capsys.readouterr()
    assert captured.out.count("\n") == 3
    assert "3 image(s)" in captured.err


def test_list_images_respects_no_recursive(image_dir: Path, capsys):
    (image_dir / "sub").mkdir()
    (image_dir / "sub" / "deep.jpg").write_bytes(b"x")
    main(["list-images", "--folder", str(image_dir), "--no-recursive"])
    assert "deep.jpg" not in capsys.readouterr().out


def test_run_cycles_the_requested_number_of_frames(image_dir: Path, capsys):
    assert main(["run", "--folder", str(image_dir), "--dry-run", "-n", "5", "-i", "0"]) == 0
    captured = capsys.readouterr()
    assert captured.out.count("\n") == 5
    assert "changed 5 wallpapers" in captured.err


def test_run_quiet_suppresses_per_frame_output(image_dir: Path, capsys):
    main(["run", "-f", str(image_dir), "--dry-run", "-n", "3", "-i", "0", "--quiet"])
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "changed 3 wallpapers" in captured.err


def test_run_accepts_fps_instead_of_interval(image_dir: Path, capsys):
    assert main(["run", "-f", str(image_dir), "--dry-run", "-n", "2", "--fps", "100"]) == 0
    assert "interval=0.01s" in capsys.readouterr().err


def test_run_rejects_a_nonsense_rate(image_dir: Path, capsys):
    assert main(["run", "-f", str(image_dir), "--dry-run", "--fps", "0"]) == 2
    assert "--fps must be greater than zero" in capsys.readouterr().err


def test_interval_and_fps_are_mutually_exclusive(image_dir: Path):
    with pytest.raises(SystemExit):
        main(["run", "-f", str(image_dir), "--fps", "10", "-i", "1"])


def test_run_on_an_empty_folder_reports_an_error(tmp_path: Path, capsys):
    assert main(["run", "--folder", str(tmp_path), "--dry-run", "-n", "1"]) == 2
    assert "no images found" in capsys.readouterr().err


def test_run_on_a_missing_folder_reports_an_error(tmp_path: Path, capsys):
    assert main(["run", "--folder", str(tmp_path / "nope"), "--dry-run"]) == 2
    assert "not a folder" in capsys.readouterr().err


def test_run_with_an_unknown_backend_reports_an_error(image_dir: Path, capsys):
    assert main(["run", "-f", str(image_dir), "-b", "banana", "-n", "1"]) == 2
    assert "unknown backend" in capsys.readouterr().err


def test_run_duration_limit(image_dir: Path, capsys):
    assert main(["run", "-f", str(image_dir), "--dry-run", "-d", "0.1", "-i", "0.01"]) == 0
    assert "changed" in capsys.readouterr().err


def test_run_shuffle_is_announced(image_dir: Path, capsys):
    main(["run", "-f", str(image_dir), "--dry-run", "-n", "3", "-i", "0", "--shuffle", "-q"])
    assert "shuffle=on" in capsys.readouterr().err


def test_resolve_images_merges_folders_and_drops_duplicates(image_dir: Path, tmp_path: Path):
    other = tmp_path / "more"
    other.mkdir()
    (other / "d.jpg").write_bytes(b"x")
    merged = resolve_images([str(image_dir), str(other), str(image_dir)])
    assert len(merged) == 4
    assert len(set(map(str, merged))) == 4


def test_resolve_images_without_folders_falls_back_to_system_wallpapers(monkeypatch):
    monkeypatch.setattr("rapidbackgroundchanger.cli.default_images", lambda: [Path("/x.jpg")])
    assert resolve_images([]) == [Path("/x.jpg")]


def test_resolve_images_raises_when_nothing_matches(tmp_path: Path):
    with pytest.raises(NoImagesFound):
        resolve_images([str(tmp_path)])


def test_gui_command_without_tkinter_explains_itself(monkeypatch, capsys):
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name.startswith("tkinter") or name.endswith(".gui"):
            raise ImportError("No module named 'tkinter'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    assert main([]) == 3
    err = capsys.readouterr().err
    assert "needs tkinter" in err
    assert "python3-tk" in err


def test_parser_default_command_is_the_gui():
    assert build_parser().parse_args([]).command is None
