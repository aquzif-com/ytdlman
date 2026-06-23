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


import os
import tarfile


def test_extract_tar_members_flattens(tmp_path):
    import ytdlman.bootstrap as bootstrap
    src = tmp_path / "ff.tar.xz"
    with tarfile.open(src, "w:xz") as tf:
        for name, data in [("ffmpeg-x/ffmpeg", b"FF"), ("ffmpeg-x/ffprobe", b"FP"),
                           ("ffmpeg-x/README", b"no")]:
            p = tmp_path / Path(name).name
            p.write_bytes(data)
            tf.add(p, arcname=name)
    out = bootstrap.extract_tar_members(src, ["ffmpeg", "ffprobe"], tmp_path / "bin")
    assert (tmp_path / "bin" / "ffmpeg").read_bytes() == b"FF"
    assert (tmp_path / "bin" / "ffprobe").read_bytes() == b"FP"
    assert {p.name for p in out} == {"ffmpeg", "ffprobe"}


def test_ensure_ytdlp_linux_saves_executable_binary(tmp_path, monkeypatch):
    import json
    import ytdlman.bootstrap as bootstrap
    from ytdlman.config import default_config
    monkeypatch.setenv("YTDLMAN_PLATFORM", "linux")
    monkeypatch.setenv("YTDLMAN_HOME", str(tmp_path))
    cfg = default_config()

    def fetch(url):
        if "releases/latest" in url:
            return json.dumps({"tag_name": "2026.06.01"}).encode()
        assert url.endswith("/yt-dlp_linux")  # linux asset, versioned URL
        return b"YTDLP-LINUX"

    status = bootstrap.ensure_ytdlp(cfg, fetch=fetch, save=lambda: None)
    target = tmp_path / "yt-dlp"          # no .exe on linux
    assert target.read_bytes() == b"YTDLP-LINUX"
    assert os.access(target, os.X_OK)     # marked executable
    assert status.present and status.version == "2026.06.01"


def test_ensure_deno_linux_uses_linux_zip(tmp_path, monkeypatch):
    import io
    import json
    import zipfile
    import ytdlman.bootstrap as bootstrap
    from ytdlman.config import default_config
    monkeypatch.setenv("YTDLMAN_PLATFORM", "linux")
    monkeypatch.setenv("YTDLMAN_HOME", str(tmp_path))
    cfg = default_config()

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("deno", b"DENO-LINUX")
    zip_bytes = buf.getvalue()

    def fetch(url):
        if "releases/latest" in url:
            return json.dumps({"tag_name": "v2.0.0"}).encode()
        assert "linux-gnu" in url
        return zip_bytes

    status = bootstrap.ensure_deno(cfg, fetch=fetch, save=lambda: None)
    target = tmp_path / "bin" / "deno"
    assert target.read_bytes() == b"DENO-LINUX"
    assert os.access(target, os.X_OK)
    assert status.present
