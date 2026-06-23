import json
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path

from .logging_setup import get_logger

STATUS_DOWNLOADED = "downloaded"
STATUS_FAILED = "failed"

_DEP_NAMES = ("yt-dlp", "ffmpeg", "deno")


@dataclass
class Track:
    video_id: str
    track_number: int
    title: str
    status: str
    file: str | None = None
    downloaded_at: str | None = None
    error: str | None = None


@dataclass
class Playlist:
    id: str
    url: str
    author: str
    album: str
    added_at: str
    last_sync: str | None = None
    next_track_number: int = 1
    tracks: list[Track] = field(default_factory=list)


@dataclass
class DependencyInfo:
    version: str | None = None
    checked_at: str | None = None


@dataclass
class Settings:
    music_dir: str = "music"
    audio_quality: str = "320"
    auto_check_updates: bool = True


@dataclass
class Config:
    settings: Settings = field(default_factory=Settings)
    dependencies: dict = field(default_factory=dict)
    playlists: list[Playlist] = field(default_factory=list)


def default_config() -> Config:
    return Config(
        settings=Settings(),
        dependencies={name: DependencyInfo() for name in _DEP_NAMES},
        playlists=[],
    )


def _config_from_dict(data: dict) -> Config:
    settings = Settings(**{**asdict(Settings()), **data.get("settings", {})})
    deps_raw = data.get("dependencies", {})
    dependencies = {name: DependencyInfo() for name in _DEP_NAMES}
    for name, info in deps_raw.items():
        dependencies[name] = DependencyInfo(
            version=info.get("version"), checked_at=info.get("checked_at")
        )
    playlists = []
    for pl in data.get("playlists", []):
        tracks = [Track(
            video_id=t["video_id"], track_number=t["track_number"], title=t["title"],
            status=t["status"], file=t.get("file"),
            downloaded_at=t.get("downloaded_at"), error=t.get("error"),
        ) for t in pl.get("tracks", [])]
        playlists.append(Playlist(
            id=pl["id"], url=pl["url"], author=pl["author"], album=pl["album"],
            added_at=pl["added_at"], last_sync=pl.get("last_sync"),
            next_track_number=pl.get("next_track_number", 1), tracks=tracks,
        ))
    return Config(settings=settings, dependencies=dependencies, playlists=playlists)


def load_config(path: Path) -> Config:
    if not path.exists():
        return default_config()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return _config_from_dict(data)
    except Exception as exc:  # corrupt / unreadable
        ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        backup = path.with_name(f"{path.name}.corrupt-{ts}")
        try:
            path.rename(backup)
        except OSError:
            backup = None
        get_logger().warning(
            "Plik config.json jest uszkodzony (%s). Utworzono kopię: %s. "
            "Startuję z czystą konfiguracją.", exc, backup,
        )
        return default_config()


def save_config(config: Config, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "settings": asdict(config.settings),
        "dependencies": {k: asdict(v) for k, v in config.dependencies.items()},
        "playlists": [asdict(p) for p in config.playlists],
    }
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)
