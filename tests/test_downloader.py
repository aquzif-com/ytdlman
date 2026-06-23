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


# New throttle and 429 detection tests
from ytdlman.downloader import (
    Throttle, RateLimitError, _is_rate_limited,
)


def test_download_command_includes_throttle_when_enabled(tmp_path):
    cmd = build_download_command(
        ytdlp=Path("yt-dlp.exe"), video_id="vid",
        out_template=str(tmp_path / "%(id)s.%(ext)s"),
        audio_quality="320", ffmpeg_dir=tmp_path, cookies=None,
        throttle=Throttle(sleep_interval=5, max_sleep_interval=20, limit_rate="1M"))
    assert "--sleep-interval" in cmd and "5" in cmd
    assert "--max-sleep-interval" in cmd and "20" in cmd
    assert "--sleep-requests" in cmd
    assert "--limit-rate" in cmd and "1M" in cmd


def test_download_command_omits_throttle_when_disabled(tmp_path):
    cmd = build_download_command(
        ytdlp=Path("yt-dlp.exe"), video_id="vid",
        out_template=str(tmp_path / "%(id)s.%(ext)s"),
        audio_quality="320", ffmpeg_dir=tmp_path, cookies=None,
        throttle=Throttle())
    assert "--sleep-interval" not in cmd
    assert "--limit-rate" not in cmd


def test_download_command_limit_rate_independent_of_sleep(tmp_path):
    cmd = build_download_command(
        ytdlp=Path("yt-dlp.exe"), video_id="vid",
        out_template=str(tmp_path / "%(id)s.%(ext)s"),
        audio_quality="320", ffmpeg_dir=tmp_path, cookies=None,
        throttle=Throttle(sleep_interval=0, max_sleep_interval=0, limit_rate="500K"))
    assert "--limit-rate" in cmd and "500K" in cmd
    assert "--sleep-interval" not in cmd


def test_entries_command_adds_sleep_requests_when_enabled():
    cmd = build_entries_command(Path("yt-dlp.exe"), "http://list", None,
                                throttle=Throttle(sleep_interval=5, max_sleep_interval=20))
    assert "--sleep-requests" in cmd
    cmd2 = build_entries_command(Path("yt-dlp.exe"), "http://list", None,
                                 throttle=Throttle())
    assert "--sleep-requests" not in cmd2


def test_is_rate_limited():
    assert _is_rate_limited("ERROR: unable: HTTP Error 429: Too Many Requests") is True
    assert _is_rate_limited("ERROR: Video unavailable") is False
    assert _is_rate_limited("") is False


def test_list_playlist_entries_raises_ratelimit_on_429():
    def runner(cmd, *, env=None):
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="HTTP Error 429: Too Many Requests")
    with pytest.raises(RateLimitError):
        list_playlist_entries(Path("yt-dlp.exe"), "http://l", None, runner=runner)


def test_list_playlist_entries_channel_url_parses(tmp_path):
    def runner(cmd, *, env=None):
        assert "https://www.youtube.com/@chan/videos" in cmd
        return subprocess.CompletedProcess(cmd, 0, stdout="a\tSong A\nb\tSong B\n", stderr="")
    entries = list_playlist_entries(Path("yt-dlp.exe"),
                                    "https://www.youtube.com/@chan/videos", None, runner=runner)
    assert [e.video_id for e in entries] == ["a", "b"]


def test_download_track_raises_ratelimit_on_429(tmp_path):
    dest = tmp_path / "alb"; dest.mkdir()
    def runner(cmd, *, env=None):
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="ERROR: HTTP Error 429: Too Many Requests")
    with pytest.raises(RateLimitError):
        download_track(PlaylistEntry("vid", "T"), dest, ytdlp=Path("yt-dlp.exe"),
                       ffmpeg_dir=tmp_path, bin_dir=tmp_path, cookies=None,
                       audio_quality="320", runner=runner)
