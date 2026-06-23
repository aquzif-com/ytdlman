import os
import re
import sys
from pathlib import Path

_ILLEGAL = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def app_dir() -> Path:
    override = os.environ.get("YTDLMAN_HOME")
    if override:
        return Path(override)
    if getattr(sys, "frozen", False):  # PyInstaller onefile
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def bin_dir() -> Path:
    return app_dir() / "bin"


def logs_dir() -> Path:
    return app_dir() / "logs"


def config_path() -> Path:
    return app_dir() / "config.json"


def cookies_path() -> Path:
    return app_dir() / "cookies.txt"


def ytdlp_path() -> Path:
    return app_dir() / "yt-dlp.exe"


def ffmpeg_dir() -> Path:
    return bin_dir()


def ffmpeg_path() -> Path:
    return bin_dir() / "ffmpeg.exe"


def ffprobe_path() -> Path:
    return bin_dir() / "ffprobe.exe"


def deno_path() -> Path:
    return bin_dir() / "deno.exe"


def music_root(music_subdir: str) -> Path:
    return app_dir() / music_subdir


def sanitize_filename(name: str) -> str:
    cleaned = _ILLEGAL.sub("", name).strip().rstrip(".")
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned or "untitled"


def album_dir(music_root: Path, author: str, album: str) -> Path:
    return music_root / sanitize_filename(author) / sanitize_filename(album)
