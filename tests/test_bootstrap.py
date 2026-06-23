import io
import json
import zipfile
from pathlib import Path
from ytdlman.config import default_config
import ytdlman.bootstrap as bootstrap


def test_github_latest_tag_parses_tag_name():
    def fetch(url):
        assert "releases/latest" in url
        return json.dumps({"tag_name": "2026.06.01"}).encode()
    assert bootstrap.github_latest_tag("yt-dlp/yt-dlp", fetch=fetch) == "2026.06.01"


def test_download_file_writes_bytes(tmp_path):
    dest = tmp_path / "out.bin"
    bootstrap.download_file("http://x", dest, fetch=lambda url: b"hello")
    assert dest.read_bytes() == b"hello"


def test_extract_members_flattens_matching_basenames(tmp_path):
    zpath = tmp_path / "a.zip"
    with zipfile.ZipFile(zpath, "w") as z:
        z.writestr("ffmpeg-x/bin/ffmpeg.exe", b"FF")
        z.writestr("ffmpeg-x/bin/ffprobe.exe", b"FP")
        z.writestr("ffmpeg-x/README", b"nope")
    out = bootstrap.extract_members(zpath, ["ffmpeg.exe", "ffprobe.exe"], tmp_path)
    assert (tmp_path / "ffmpeg.exe").read_bytes() == b"FF"
    assert (tmp_path / "ffprobe.exe").read_bytes() == b"FP"
    assert set(p.name for p in out) == {"ffmpeg.exe", "ffprobe.exe"}


def test_ensure_ytdlp_downloads_when_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("YTDLMAN_PLATFORM", "windows")
    monkeypatch.setenv("YTDLMAN_HOME", str(tmp_path))
    cfg = default_config()
    calls = {"n": 0}
    def fetch(url):
        calls["n"] += 1
        if "releases/latest" in url:
            return json.dumps({"tag_name": "2026.06.01"}).encode()
        return b"YTDLP-BINARY"
    status = bootstrap.ensure_ytdlp(cfg, fetch=fetch, save=lambda: None)
    assert (tmp_path / "yt-dlp.exe").read_bytes() == b"YTDLP-BINARY"
    assert status.present and status.version == "2026.06.01"
    assert cfg.dependencies["yt-dlp"].version == "2026.06.01"


def test_current_status_reports_presence(tmp_path, monkeypatch):
    monkeypatch.setenv("YTDLMAN_PLATFORM", "windows")
    monkeypatch.setenv("YTDLMAN_HOME", str(tmp_path))
    cfg = default_config()
    statuses = {s.name: s for s in bootstrap.current_status(cfg)}
    assert statuses["yt-dlp"].present is False
    (tmp_path / "yt-dlp.exe").write_bytes(b"x")
    statuses = {s.name: s for s in bootstrap.current_status(cfg)}
    assert statuses["yt-dlp"].present is True
