import os
from pathlib import Path
import ytdlman.platform_target as pt


def test_target_os_honors_env_override(monkeypatch):
    monkeypatch.setenv("YTDLMAN_PLATFORM", "windows")
    assert pt.target_os() == "windows"
    assert pt.is_windows() is True
    assert pt.exe_suffix() == ".exe"
    monkeypatch.setenv("YTDLMAN_PLATFORM", "linux")
    assert pt.target_os() == "linux"
    assert pt.is_windows() is False
    assert pt.exe_suffix() == ""


def test_target_os_autodetects_from_sys_platform(monkeypatch):
    monkeypatch.delenv("YTDLMAN_PLATFORM", raising=False)
    monkeypatch.setattr(pt.sys, "platform", "win32")
    assert pt.target_os() == "windows"
    monkeypatch.setattr(pt.sys, "platform", "linux")
    assert pt.target_os() == "linux"
    monkeypatch.setattr(pt.sys, "platform", "darwin")
    assert pt.target_os() == "linux"  # macOS treated as linux for code paths


def test_make_executable_sets_bit_on_linux(monkeypatch, tmp_path):
    monkeypatch.setenv("YTDLMAN_PLATFORM", "linux")
    f = tmp_path / "bin"
    f.write_bytes(b"x")
    pt.make_executable(f)
    assert os.access(f, os.X_OK)


def test_make_executable_noop_on_windows(monkeypatch, tmp_path):
    monkeypatch.setenv("YTDLMAN_PLATFORM", "windows")
    f = tmp_path / "bin"
    f.write_bytes(b"x")
    pt.make_executable(f)  # must not raise


def test_make_executable_missing_file_noop(monkeypatch, tmp_path):
    monkeypatch.setenv("YTDLMAN_PLATFORM", "linux")
    pt.make_executable(tmp_path / "nope")  # must not raise
