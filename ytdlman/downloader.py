import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .logging_setup import get_logger


@dataclass
class PlaylistEntry:
    video_id: str
    title: str


@dataclass
class TrackFiles:
    audio: Path
    info_json: Path | None
    thumbnail: Path | None


class DownloadError(Exception):
    pass


def parse_flat_playlist(output: str) -> list[PlaylistEntry]:
    entries = []
    for line in output.splitlines():
        line = line.rstrip("\n")
        if not line.strip():
            continue
        video_id, _, title = line.partition("\t")
        entries.append(PlaylistEntry(video_id.strip(), title))
    return entries


def build_entries_command(ytdlp: Path, url: str, cookies: Path | None) -> list[str]:
    cmd = [str(ytdlp), "--flat-playlist", "--no-warnings",
           "--print", "%(id)s\t%(title)s"]
    if cookies and Path(cookies).exists():
        cmd += ["--cookies", str(cookies)]
    cmd.append(url)
    return cmd


def build_download_command(*, ytdlp: Path, video_id: str, out_template: str,
                           audio_quality: str, ffmpeg_dir: Path,
                           cookies: Path | None) -> list[str]:
    cmd = [
        str(ytdlp),
        "-x", "--audio-format", "mp3", "--audio-quality", f"{audio_quality}K",
        "--no-playlist", "--no-warnings",
        "--write-info-json", "--write-thumbnail", "--convert-thumbnails", "jpg",
        "--ffmpeg-location", str(ffmpeg_dir),
        "-o", out_template,
    ]
    if cookies and Path(cookies).exists():
        cmd += ["--cookies", str(cookies)]
    cmd.append(f"https://www.youtube.com/watch?v={video_id}")
    return cmd


def download_env(bin_dir: Path) -> dict:
    env = dict(os.environ)
    env["PATH"] = str(bin_dir) + os.pathsep + env.get("PATH", "")
    return env


def run_command(cmd, *, env=None) -> subprocess.CompletedProcess:
    get_logger().debug("Uruchamiam: %s", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True, env=env)
    get_logger().debug("Kod wyjścia=%s stderr=%s", result.returncode,
                       result.stderr.strip()[:500])
    return result


def list_playlist_entries(ytdlp: Path, url: str, cookies: Path | None, *,
                          runner=run_command) -> list[PlaylistEntry]:
    cmd = build_entries_command(ytdlp, url, cookies)
    result = runner(cmd, env=None)
    if result.returncode != 0:
        raise DownloadError(
            f"Nie udało się pobrać listy playlisty (kod {result.returncode}). "
            f"Szczegóły w logu."
        )
    return parse_flat_playlist(result.stdout)


def download_track(entry: PlaylistEntry, dest_dir: Path, *, ytdlp: Path,
                   ffmpeg_dir: Path, bin_dir: Path, cookies: Path | None,
                   audio_quality: str, runner=run_command) -> TrackFiles:
    dest_dir.mkdir(parents=True, exist_ok=True)
    out_template = str(dest_dir / "%(id)s.%(ext)s")
    cmd = build_download_command(
        ytdlp=ytdlp, video_id=entry.video_id, out_template=out_template,
        audio_quality=audio_quality, ffmpeg_dir=ffmpeg_dir, cookies=cookies)
    result = runner(cmd, env=download_env(bin_dir))
    audio = dest_dir / f"{entry.video_id}.mp3"
    if result.returncode != 0 or not audio.exists():
        raise DownloadError(
            f"Pobieranie '{entry.title}' nie powiodło się "
            f"(kod {result.returncode}). Szczegóły w logu."
        )
    info = dest_dir / f"{entry.video_id}.info.json"
    thumb = dest_dir / f"{entry.video_id}.jpg"
    return TrackFiles(
        audio=audio,
        info_json=info if info.exists() else None,
        thumbnail=thumb if thumb.exists() else None,
    )
