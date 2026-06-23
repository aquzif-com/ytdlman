from pathlib import Path
from ytdlman.config import Config, Settings, Playlist, Track, STATUS_DOWNLOADED, STATUS_FAILED
from ytdlman.downloader import PlaylistEntry, TrackFiles
from ytdlman.sync import (
    find_new_entries, reserve_track_number, upsert_track, sync_playlist,
)


def _playlist(**kw):
    base = dict(id="p", url="http://l", author="Me", album="Alb", added_at="t")
    base.update(kw)
    return Playlist(**base)


def test_find_new_entries_skips_downloaded_keeps_failed():
    pl = _playlist(tracks=[
        Track(video_id="a", track_number=1, title="A", status=STATUS_DOWNLOADED),
        Track(video_id="b", track_number=2, title="B", status=STATUS_FAILED),
    ])
    entries = [PlaylistEntry("a", "A"), PlaylistEntry("b", "B"), PlaylistEntry("c", "C")]
    new = find_new_entries(pl, entries)
    assert [e.video_id for e in new] == ["b", "c"]


def test_reserve_track_number_increments():
    pl = _playlist(next_track_number=5)
    assert reserve_track_number(pl) == 5
    assert pl.next_track_number == 6


def test_upsert_replaces_existing_by_video_id():
    pl = _playlist(tracks=[Track(video_id="a", track_number=1, title="old",
                                 status=STATUS_FAILED)])
    upsert_track(pl, Track(video_id="a", track_number=1, title="new",
                           status=STATUS_DOWNLOADED))
    assert len(pl.tracks) == 1
    assert pl.tracks[0].status == STATUS_DOWNLOADED


def test_sync_playlist_downloads_new_tags_and_persists(tmp_path, monkeypatch):
    import ytdlman.sync as sync
    monkeypatch.setattr(sync, "now_iso", lambda: "TS")
    # avoid touching real mp3 files when writing tags
    monkeypatch.setattr(sync, "write_tags", lambda *a, **k: None)

    cfg = Config(settings=Settings(), dependencies={}, playlists=[])
    pl = _playlist()
    cfg.playlists.append(pl)
    music_root = tmp_path / "music"

    saves = {"n": 0}
    def save():
        saves["n"] += 1

    def entries_provider(url):
        return [PlaylistEntry("v1", "Title One (Official Video)")]

    def track_downloader(entry, dest_dir, track_number):
        dest_dir.mkdir(parents=True, exist_ok=True)
        audio = dest_dir / f"{entry.video_id}.mp3"
        audio.write_bytes(b"\xff\xfb")
        info = dest_dir / f"{entry.video_id}.info.json"
        info.write_text('{"upload_date":"20240101"}', encoding="utf-8")
        thumb = dest_dir / f"{entry.video_id}.jpg"
        thumb.write_bytes(b"\xff\xd8")
        return TrackFiles(audio=audio, info_json=info, thumbnail=thumb)

    result = sync_playlist(
        cfg, pl, music_root=music_root, ytdlp=Path("yt-dlp.exe"),
        ffmpeg_dir=tmp_path, bin_dir=tmp_path, cookies=None, save=save,
        entries_provider=entries_provider, track_downloader=track_downloader)

    assert result.downloaded == 1 and result.failed == 0
    track = pl.tracks[0]
    assert track.status == STATUS_DOWNLOADED
    assert track.title == "Title One"           # cleaned
    assert track.track_number == 1
    final = music_root / "Me" / "Alb" / "01 - Title One.mp3"
    assert final.exists()
    assert (music_root / "Me" / "Alb" / "folder.jpg").exists()
    assert pl.last_sync == "TS"
    assert saves["n"] >= 3                        # reserve + downloaded + last_sync


def test_sync_playlist_marks_failed_and_continues(tmp_path):
    from ytdlman.downloader import DownloadError
    cfg = Config(settings=Settings(), dependencies={}, playlists=[])
    pl = _playlist()
    cfg.playlists.append(pl)

    def entries_provider(url):
        return [PlaylistEntry("bad", "Bad")]

    def track_downloader(entry, dest_dir, track_number):
        raise DownloadError("nope")

    result = sync_playlist(
        cfg, pl, music_root=tmp_path / "music", ytdlp=Path("yt-dlp.exe"),
        ffmpeg_dir=tmp_path, bin_dir=tmp_path, cookies=None, save=lambda: None,
        entries_provider=entries_provider, track_downloader=track_downloader)

    assert result.failed == 1
    assert pl.tracks[0].status == STATUS_FAILED
    assert pl.tracks[0].error


import pytest
from ytdlman.downloader import RateLimitError, PlaylistEntry


def test_sync_playlist_aborts_and_rolls_back_on_ratelimit(tmp_path):
    cfg = Config(settings=Settings(), dependencies={}, playlists=[])
    pl = _playlist(next_track_number=1)
    cfg.playlists.append(pl)

    def entries_provider(url):
        return [PlaylistEntry("v1", "Song"), PlaylistEntry("v2", "Song 2")]

    def track_downloader(entry, dest_dir, track_number):
        raise RateLimitError("429")

    with pytest.raises(RateLimitError):
        sync_playlist(
            cfg, pl, music_root=tmp_path / "music", ytdlp=__import__("pathlib").Path("yt-dlp.exe"),
            ffmpeg_dir=tmp_path, bin_dir=tmp_path, cookies=None, save=lambda: None,
            entries_provider=entries_provider, track_downloader=track_downloader)

    # reserved number rolled back; no failed track recorded; not advanced
    assert pl.next_track_number == 1
    assert pl.tracks == []


def test_sync_playlist_aborts_on_ratelimit_during_listing(tmp_path):
    cfg = Config(settings=Settings(), dependencies={}, playlists=[])
    pl = _playlist()
    cfg.playlists.append(pl)

    def entries_provider(url):
        raise RateLimitError("429 while listing")

    with pytest.raises(RateLimitError):
        sync_playlist(
            cfg, pl, music_root=tmp_path / "music", ytdlp=__import__("pathlib").Path("yt-dlp.exe"),
            ffmpeg_dir=tmp_path, bin_dir=tmp_path, cookies=None, save=lambda: None,
            entries_provider=entries_provider, track_downloader=lambda *a: None)
