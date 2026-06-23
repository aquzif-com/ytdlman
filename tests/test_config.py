from pathlib import Path
from ytdlman.config import (
    Config, Playlist, Track, default_config, load_config, save_config,
    STATUS_DOWNLOADED,
)


def test_save_then_load_roundtrip(tmp_path):
    cfg = default_config()
    cfg.playlists.append(Playlist(
        id="p1", url="http://x", author="Me", album="Album", added_at="t",
        next_track_number=2,
        tracks=[Track(video_id="v1", track_number=1, title="T",
                      status=STATUS_DOWNLOADED, file="music/Me/Album/01 - T.mp3")],
    ))
    p = tmp_path / "config.json"
    save_config(cfg, p)
    loaded = load_config(p)
    assert loaded.playlists[0].tracks[0].video_id == "v1"
    assert loaded.playlists[0].next_track_number == 2
    assert loaded.settings.audio_quality == "320"


def test_save_is_atomic_no_tmp_left(tmp_path):
    p = tmp_path / "config.json"
    save_config(default_config(), p)
    assert p.exists()
    assert not (tmp_path / "config.json.tmp").exists()


def test_load_missing_returns_default(tmp_path):
    cfg = load_config(tmp_path / "nope.json")
    assert cfg.playlists == []


def test_load_corrupt_backs_up_and_returns_default(tmp_path):
    p = tmp_path / "config.json"
    p.write_text("{ not json", encoding="utf-8")
    cfg = load_config(p)
    assert isinstance(cfg, Config)
    assert cfg.playlists == []
    backups = list(tmp_path.glob("config.json.corrupt-*"))
    assert len(backups) == 1
