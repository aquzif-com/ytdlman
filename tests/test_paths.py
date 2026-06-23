from pathlib import Path
import ytdlman.paths as paths


def test_app_dir_honors_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("YTDLMAN_HOME", str(tmp_path))
    assert paths.app_dir() == tmp_path


def test_derived_paths_windows(monkeypatch, tmp_path):
    monkeypatch.setenv("YTDLMAN_HOME", str(tmp_path))
    monkeypatch.setenv("YTDLMAN_PLATFORM", "windows")
    assert paths.bin_dir() == tmp_path / "bin"
    assert paths.logs_dir() == tmp_path / "logs"
    assert paths.config_path() == tmp_path / "config.json"
    assert paths.cookies_path() == tmp_path / "cookies.txt"
    assert paths.ytdlp_path() == tmp_path / "yt-dlp.exe"
    assert paths.ffmpeg_path() == tmp_path / "bin" / "ffmpeg.exe"
    assert paths.ffprobe_path() == tmp_path / "bin" / "ffprobe.exe"
    assert paths.deno_path() == tmp_path / "bin" / "deno.exe"


def test_derived_paths_linux(monkeypatch, tmp_path):
    monkeypatch.setenv("YTDLMAN_HOME", str(tmp_path))
    monkeypatch.setenv("YTDLMAN_PLATFORM", "linux")
    assert paths.ytdlp_path() == tmp_path / "yt-dlp"
    assert paths.ffmpeg_path() == tmp_path / "bin" / "ffmpeg"
    assert paths.ffprobe_path() == tmp_path / "bin" / "ffprobe"
    assert paths.deno_path() == tmp_path / "bin" / "deno"


def test_sanitize_filename_strips_illegal_chars():
    assert paths.sanitize_filename('a/b:c*?"<>|d') == "abcd"


def test_sanitize_filename_never_empty():
    assert paths.sanitize_filename("///") == "untitled"


def test_album_dir_nests_author_then_album(monkeypatch, tmp_path):
    root = tmp_path / "music"
    assert paths.album_dir(root, "AC/DC", "Greatest: Hits") == root / "ACDC" / "Greatest Hits"
