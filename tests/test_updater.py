import json
from ytdlman.updater import (
    parse_version, is_newer, check_for_update, apply_update,
    cleanup_old_executable, UpdateCheck, UpdateError,
)


def test_parse_version():
    assert parse_version("v0.1.2") == (0, 1, 2)
    assert parse_version("1.2.3") == (1, 2, 3)
    assert parse_version("V2.0") == (2, 0)


def test_is_newer():
    assert is_newer("v0.1.2", "0.1.1") is True
    assert is_newer("0.2.0", "0.1.9") is True
    assert is_newer("v0.1.0", "0.1.1") is False
    assert is_newer("0.1.1", "0.1.1") is False


def test_check_for_update_detects_newer():
    def fetch(url):
        assert "releases/latest" in url
        return json.dumps({"tag_name": "v0.2.0"}).encode()
    chk = check_for_update("0.1.1", fetch=fetch)
    assert chk == UpdateCheck(current="0.1.1", latest="v0.2.0", available=True)


def test_check_for_update_not_newer():
    def fetch(url):
        return json.dumps({"tag_name": "v0.1.1"}).encode()
    chk = check_for_update("0.1.1", fetch=fetch)
    assert chk.available is False


def test_check_for_update_handles_network_error():
    def fetch(url):
        raise OSError("no network")
    chk = check_for_update("0.1.1", fetch=fetch)
    assert chk.latest is None
    assert chk.available is False


def test_apply_update_swaps_in_new_exe(tmp_path):
    exe = tmp_path / "ytdlman.exe"
    exe.write_bytes(b"OLD")
    result = apply_update(exe, fetch=lambda url: b"NEW", download_url="http://x")
    assert result == exe
    assert exe.read_bytes() == b"NEW"
    assert (tmp_path / "ytdlman.old.exe").read_bytes() == b"OLD"
    assert not (tmp_path / "ytdlman.new.exe").exists()


def test_apply_update_download_failure_raises_and_keeps_exe(tmp_path):
    exe = tmp_path / "ytdlman.exe"
    exe.write_bytes(b"OLD")

    def fetch(url):
        raise OSError("boom")

    try:
        apply_update(exe, fetch=fetch, download_url="http://x")
        assert False, "expected UpdateError"
    except UpdateError:
        pass
    assert exe.read_bytes() == b"OLD"  # original untouched


def test_cleanup_removes_old_executable(tmp_path):
    exe = tmp_path / "ytdlman.exe"
    old = tmp_path / "ytdlman.old.exe"
    old.write_bytes(b"stale")
    cleanup_old_executable(exe)
    assert not old.exists()


def test_cleanup_noop_when_no_old(tmp_path):
    exe = tmp_path / "ytdlman.exe"
    cleanup_old_executable(exe)  # must not raise


import os


def test_release_asset_url_per_platform(monkeypatch):
    import ytdlman.updater as updater
    monkeypatch.setenv("YTDLMAN_PLATFORM", "windows")
    assert updater.release_asset_url().endswith("/ytdlman.exe")
    monkeypatch.setenv("YTDLMAN_PLATFORM", "linux")
    assert updater.release_asset_url().endswith("/ytdlman-linux")


def test_apply_update_marks_executable_on_linux(monkeypatch, tmp_path):
    import ytdlman.updater as updater
    monkeypatch.setenv("YTDLMAN_PLATFORM", "linux")
    exe = tmp_path / "ytdlman-linux"
    exe.write_bytes(b"OLD")
    result = updater.apply_update(exe, fetch=lambda url: b"NEW", download_url="http://x")
    assert result == exe
    assert exe.read_bytes() == b"NEW"
    assert os.access(exe, os.X_OK)
