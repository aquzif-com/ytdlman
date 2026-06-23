import json
from dataclasses import dataclass
from pathlib import Path

from .clock import now_iso
from .config import Config, Playlist, Track, STATUS_DOWNLOADED, STATUS_FAILED
from .downloader import (
    PlaylistEntry, TrackFiles, DownloadError,
    list_playlist_entries, download_track,
)
from .logging_setup import get_logger
from .metadata import clean_title, extract_year, write_tags
from .paths import album_dir, sanitize_filename


@dataclass
class SyncResult:
    downloaded: int
    failed: int


def find_new_entries(playlist: Playlist, entries: list[PlaylistEntry]) -> list[PlaylistEntry]:
    done = {t.video_id for t in playlist.tracks if t.status == STATUS_DOWNLOADED}
    return [e for e in entries if e.video_id not in done]


def reserve_track_number(playlist: Playlist) -> int:
    number = playlist.next_track_number
    playlist.next_track_number += 1
    return number


def upsert_track(playlist: Playlist, track: Track) -> None:
    for i, existing in enumerate(playlist.tracks):
        if existing.video_id == track.video_id:
            playlist.tracks[i] = track
            return
    playlist.tracks.append(track)


def read_year(info_json: Path | None) -> str | None:
    if not info_json or not info_json.exists():
        return None
    try:
        data = json.loads(info_json.read_text(encoding="utf-8"))
        return extract_year(data.get("upload_date"))
    except Exception:
        return None


def _cleanup(*files: Path | None) -> None:
    for f in files:
        try:
            if f and f.exists():
                f.unlink()
        except OSError:
            pass


def sync_playlist(config: Config, playlist: Playlist, *, music_root: Path,
                  ytdlp: Path, ffmpeg_dir: Path, bin_dir: Path,
                  cookies: Path | None, save, entries_provider=None,
                  track_downloader=None, on_progress=None) -> SyncResult:
    log = get_logger()
    if entries_provider is None:
        entries_provider = lambda url: list_playlist_entries(ytdlp, url, cookies)
    if track_downloader is None:
        track_downloader = lambda entry, dest, number: download_track(
            entry, dest, ytdlp=ytdlp, ffmpeg_dir=ffmpeg_dir, bin_dir=bin_dir,
            cookies=cookies, audio_quality=config.settings.audio_quality)

    entries = entries_provider(playlist.url)
    new = find_new_entries(playlist, entries)
    dest = album_dir(music_root, playlist.author, playlist.album)
    downloaded = failed = 0

    for index, entry in enumerate(new, start=1):
        if on_progress:
            on_progress(index, len(new), entry.title)
        number = reserve_track_number(playlist)
        save()  # persist reserved number before doing work
        try:
            files = track_downloader(entry, dest, number)
            title = clean_title(entry.title)
            year = read_year(files.info_json)
            cover = files.thumbnail.read_bytes() if files.thumbnail else None
            final = dest / f"{number:02d} - {sanitize_filename(title)}.mp3"
            write_tags(files.audio, artist=playlist.author, album=playlist.album,
                       title=title, track_number=number, year=year, cover_jpeg=cover)
            files.audio.replace(final)
            folder_jpg = dest / "folder.jpg"
            if cover and not folder_jpg.exists():
                folder_jpg.write_bytes(cover)
            _cleanup(files.info_json, files.thumbnail)
            upsert_track(playlist, Track(
                video_id=entry.video_id, track_number=number, title=title,
                status=STATUS_DOWNLOADED, file=str(final), downloaded_at=now_iso()))
            downloaded += 1
            log.info("[green]Pobrano[/green] %02d - %s", number, title)
        except Exception as exc:
            upsert_track(playlist, Track(
                video_id=entry.video_id, track_number=number,
                title=clean_title(entry.title), status=STATUS_FAILED,
                error=str(exc)))
            failed += 1
            log.error("[red]Błąd[/red] '%s': %s", entry.title, exc)
        finally:
            save()  # persist outcome after every track

    playlist.last_sync = now_iso()
    save()
    return SyncResult(downloaded=downloaded, failed=failed)


def sync_all(config: Config, *, music_root: Path, ytdlp: Path, ffmpeg_dir: Path,
             bin_dir: Path, cookies: Path | None, save, on_progress=None) -> dict:
    results = {}
    for playlist in config.playlists:
        get_logger().info("[bold]Synchronizuję[/bold]: %s — %s",
                          playlist.author, playlist.album)
        results[playlist.id] = sync_playlist(
            config, playlist, music_root=music_root, ytdlp=ytdlp,
            ffmpeg_dir=ffmpeg_dir, bin_dir=bin_dir, cookies=cookies, save=save,
            on_progress=on_progress)
    return results
