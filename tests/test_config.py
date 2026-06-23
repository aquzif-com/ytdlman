import pytest
from pathlib import Path
from ytdlman.config import (
    Config, Playlist, Track, default_config, load_config, save_config,
    STATUS_DOWNLOADED, Settings, validate_throttle, AuthConfig,
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


def test_settings_has_throttle_defaults():
    s = Settings()
    assert s.sleep_interval == 5
    assert s.max_sleep_interval == 20
    assert s.limit_rate == ""


def test_old_config_without_throttle_loads_with_defaults(tmp_path):
    p = tmp_path / "config.json"
    p.write_text(
        '{"settings": {"music_dir": "music", "audio_quality": "320", '
        '"auto_check_updates": true}, "dependencies": {}, "playlists": []}',
        encoding="utf-8",
    )
    cfg = load_config(p)
    assert cfg.settings.sleep_interval == 5
    assert cfg.settings.max_sleep_interval == 20
    assert cfg.settings.limit_rate == ""


def test_throttle_fields_roundtrip(tmp_path):
    cfg = default_config()
    cfg.settings.sleep_interval = 3
    cfg.settings.max_sleep_interval = 12
    cfg.settings.limit_rate = "1M"
    p = tmp_path / "config.json"
    save_config(cfg, p)
    loaded = load_config(p)
    assert loaded.settings.sleep_interval == 3
    assert loaded.settings.max_sleep_interval == 12
    assert loaded.settings.limit_rate == "1M"


def test_validate_throttle_ok():
    assert validate_throttle("5", "20", "1M") == (5, 20, "1M")
    assert validate_throttle("0", "0", "") == (0, 0, "")
    assert validate_throttle("2", "2", "1m") == (2, 2, "1M")  # normalized upper-case


@pytest.mark.parametrize("sleep,mx,limit", [
    ("x", "20", ""),     # non-int sleep
    ("5", "y", ""),      # non-int max
    ("-1", "5", ""),     # negative
    ("20", "5", ""),     # max < min
    ("5", "20", "abc"),  # bad rate
    ("5", "20", "1Q"),   # bad rate suffix
])
def test_validate_throttle_rejects(sleep, mx, limit):
    with pytest.raises(ValueError):
        validate_throttle(sleep, mx, limit)


def test_auth_defaults_empty():
    a = AuthConfig()
    assert a.username is None and a.password_hash is None
    assert a.salt is None and a.secret_key is None
    assert a.iterations == 200000


def test_config_has_auth_section():
    assert isinstance(default_config().auth, AuthConfig)


def test_auth_roundtrip(tmp_path):
    cfg = default_config()
    cfg.auth.username = "admin"
    cfg.auth.password_hash = "deadbeef"
    cfg.auth.salt = "abcd"
    cfg.auth.secret_key = "key123"
    p = tmp_path / "config.json"
    save_config(cfg, p)
    loaded = load_config(p)
    assert loaded.auth.username == "admin"
    assert loaded.auth.password_hash == "deadbeef"
    assert loaded.auth.salt == "abcd"
    assert loaded.auth.secret_key == "key123"


def test_old_config_without_auth_loads_empty(tmp_path):
    p = tmp_path / "config.json"
    p.write_text(
        '{"settings": {}, "dependencies": {}, "playlists": []}', encoding="utf-8")
    cfg = load_config(p)
    assert cfg.auth.username is None
    assert cfg.auth.iterations == 200000
