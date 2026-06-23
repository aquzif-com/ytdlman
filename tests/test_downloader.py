import subprocess
from pathlib import Path
import pytest
from ytdlman.downloader import (
    PlaylistEntry, parse_flat_playlist, build_entries_command,
    build_download_command, download_env, list_playlist_entries,
    download_track, DownloadError,
)


def test_parse_flat_playlist():
    out = "abc\tFirst Song\ndef\tSecond | Official Video\n\n"
    entries = parse_flat_playlist(out)
    assert entries == [PlaylistEntry("abc", "First Song"),
                       PlaylistEntry("def", "Second | Official Video")]


def test_build_entries_command_includes_cookies(tmp_path):
    cookies = tmp_path / "cookies.txt"
    cookies.write_text("x", encoding="utf-8")
    cmd = build_entries_command(Path("yt-dlp.exe"), "http://list", cookies)
    assert "--flat-playlist" in cmd
    assert "--cookies" in cmd and str(cookies) in cmd
    assert "http://list" in cmd


def test_build_entries_command_omits_cookies_when_absent():
    cmd = build_entries_command(Path("yt-dlp.exe"), "http://list", None)
    assert "--cookies" not in cmd


def test_build_download_command_uses_quality_and_ffmpeg(tmp_path):
    cmd = build_download_command(
        ytdlp=Path("yt-dlp.exe"), video_id="vid",
        out_template=str(tmp_path / "%(id)s.%(ext)s"),
        audio_quality="320", ffmpeg_dir=tmp_path, cookies=None)
    assert "-x" in cmd
    assert "mp3" in cmd
    assert "320K" in cmd
    assert "--ffmpeg-location" in cmd
    assert "https://www.youtube.com/watch?v=vid" in cmd


def test_download_env_prepends_bin(monkeypatch, tmp_path):
    monkeypatch.setenv("PATH", "/usr/bin")
    env = download_env(tmp_path)
    assert env["PATH"].startswith(str(tmp_path))


def test_list_playlist_entries_uses_runner():
    def fake_runner(cmd, *, env=None):
        return subprocess.CompletedProcess(cmd, 0, stdout="x\tTitle\n", stderr="")
    entries = list_playlist_entries(Path("yt-dlp.exe"), "http://l", None,
                                    runner=fake_runner)
    assert entries == [PlaylistEntry("x", "Title")]


def test_download_track_returns_located_files(tmp_path):
    dest = tmp_path / "alb"
    dest.mkdir()

    def fake_runner(cmd, *, env=None):
        (dest / "vid.mp3").write_bytes(b"\xff\xfb")
        (dest / "vid.info.json").write_text('{"upload_date":"20240101"}', encoding="utf-8")
        (dest / "vid.jpg").write_bytes(b"\xff\xd8")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    files = download_track(
        PlaylistEntry("vid", "T"), dest, ytdlp=Path("yt-dlp.exe"),
        ffmpeg_dir=tmp_path, bin_dir=tmp_path, cookies=None,
        audio_quality="320", runner=fake_runner)
    assert files.audio == dest / "vid.mp3"
    assert files.info_json == dest / "vid.info.json"
    assert files.thumbnail == dest / "vid.jpg"


def test_download_track_raises_when_audio_missing(tmp_path):
    dest = tmp_path / "alb"
    dest.mkdir()

    def fake_runner(cmd, *, env=None):
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="boom")

    with pytest.raises(DownloadError):
        download_track(PlaylistEntry("vid", "T"), dest, ytdlp=Path("yt-dlp.exe"),
                       ffmpeg_dir=tmp_path, bin_dir=tmp_path, cookies=None,
                       audio_quality="320", runner=fake_runner)
