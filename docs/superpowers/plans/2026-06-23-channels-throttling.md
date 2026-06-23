# Channels + Throttling + 429-Stop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let YTDLMAN download whole YouTube channels (same flow as playlists) "politely" — configurable inter-track delays passed to yt-dlp — and stop cleanly on HTTP 429 with a message and a pause back to the menu.

**Architecture:** Adds throttle settings to the existing `Settings` model, threads a `Throttle` value object into the yt-dlp command builders, detects 429 in yt-dlp stderr as a dedicated `RateLimitError`, and makes `sync` abort the whole run (rolling back the reserved track number) on that error while `app` shows a message + `pause()` and returns to the menu. Channels need no new code — a channel URL flows through the existing add/sync path; we only add a test documenting it.

**Tech Stack:** Python 3.12, existing `ytdlman` package, `questionary`/`rich`, `pytest`. No new dependencies.

## Global Constraints

- All work builds on the existing codebase (branch `dev`); follow existing patterns. Run tests with `.venv/bin/python -m pytest`.
- All user-facing text is Polish (intentional).
- `config.json` is written atomically and after every action (existing `save()` callable).
- New `Settings` fields with defaults: `sleep_interval=5`, `max_sleep_interval=20`, `limit_rate=""`. An old `config.json` lacking these must load with the defaults (backward compatibility).
- yt-dlp throttle mapping: when `sleep_interval > 0` → `--sleep-interval <min> --max-sleep-interval <max> --sleep-requests 1`; when `sleep_interval == 0` those flags are omitted. `limit_rate` non-empty → `--limit-rate <value>` (independent of sleep). `max_sleep_interval` effectively `max(max_sleep_interval, sleep_interval)`.
- Validation: `sleep_interval`/`max_sleep_interval` are integers ≥ 0, `max_sleep_interval ≥ sleep_interval`; `limit_rate` is `""` or matches `^\d+[KMG]?$` (normalized to upper-case).
- 429 detection: yt-dlp stderr contains any of `HTTP Error 429`, `Too Many Requests`, `429` (case-insensitive) → `RateLimitError(DownloadError)`.
- 429 behavior: abort the entire sync; do NOT mark the in-flight track `failed`; roll back the reserved `next_track_number`; propagate `RateLimitError` out of `sync_playlist` and `sync_all`; `app` shows the message, calls `pause()`, returns to the menu. Already-downloaded tracks are kept.
- Channels: no new code path — a channel URL (`https://www.youtube.com/@name`, `.../@name/videos`) is just another source through the existing flow. Add a test confirming listing works.

---

## File Structure

```
ytdlman/config.py        # + sleep_interval/max_sleep_interval/limit_rate fields; + validate_throttle()
ytdlman/downloader.py     # + Throttle dataclass; throttle args in build_*; RateLimitError + _is_rate_limited
ytdlman/sync.py           # thread Throttle from settings; RateLimitError abort + track-number rollback
ytdlman/ui.py             # + pause(); + edit_settings()
ytdlman/app.py            # catch RateLimitError around sync; editable settings handler
tests/test_config.py      # + throttle fields + validate_throttle + backward-compat
tests/test_downloader.py  # + throttle args + 429 detection + channel listing
tests/test_sync.py        # + RateLimitError abort + rollback
```

---

### Task 1: Settings throttle fields + validation

**Files:**
- Modify: `ytdlman/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: existing `Settings`, `_config_from_dict`, `default_config`.
- Produces:
  - `Settings` gains `sleep_interval: int = 5`, `max_sleep_interval: int = 20`, `limit_rate: str = ""`.
  - `validate_throttle(sleep_raw, max_raw, limit_raw) -> tuple[int, int, str]` — parses/validates user input (any stringable), raises `ValueError` (Polish message) on bad input, returns normalized `(sleep_interval, max_sleep_interval, limit_rate)`.

- [ ] **Step 1: Write the failing tests** — append to `tests/test_config.py`

```python
import pytest
from ytdlman.config import Settings, default_config, load_config, save_config, validate_throttle


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_config.py -k throttle -v`
Expected: FAIL — `ImportError: cannot import name 'validate_throttle'` (and Settings has no throttle fields)

- [ ] **Step 3: Add the fields** — in `ytdlman/config.py`, extend the `Settings` dataclass:

```python
@dataclass
class Settings:
    music_dir: str = "music"
    audio_quality: str = "320"
    auto_check_updates: bool = True
    sleep_interval: int = 5
    max_sleep_interval: int = 20
    limit_rate: str = ""
```

- [ ] **Step 4: Add `validate_throttle`** — add near the top of `ytdlman/config.py` (after the imports; add `import re` to the existing imports):

```python
def validate_throttle(sleep_raw, max_raw, limit_raw) -> tuple[int, int, str]:
    """Parse and validate throttle settings from (possibly string) user input.

    Returns the normalized (sleep_interval, max_sleep_interval, limit_rate).
    Raises ValueError with a Polish message on invalid input.
    """
    try:
        sleep = int(str(sleep_raw).strip())
    except ValueError:
        raise ValueError("Przerwa min musi być liczbą całkowitą ≥ 0.")
    try:
        maximum = int(str(max_raw).strip())
    except ValueError:
        raise ValueError("Przerwa max musi być liczbą całkowitą ≥ 0.")
    if sleep < 0 or maximum < 0:
        raise ValueError("Przerwy muszą być ≥ 0.")
    if maximum < sleep:
        raise ValueError("Przerwa max musi być ≥ przerwy min.")
    limit = str(limit_raw).strip().upper()
    if limit and not re.fullmatch(r"\d+[KMG]?", limit):
        raise ValueError("Limit pasma musi być puste lub w formacie 500K / 1M.")
    return sleep, maximum, limit
```

Note: backward compatibility already works because `_config_from_dict` merges over `asdict(Settings())`, so missing keys fall back to the new defaults. No change needed there.

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_config.py -v`
Expected: PASS (existing config tests + new throttle tests)

- [ ] **Step 6: Commit**

```bash
git add ytdlman/config.py tests/test_config.py
git commit -m "feat: add throttle settings (sleep/limit_rate) with validation"
```

---

### Task 2: Throttle in yt-dlp commands + 429 detection + channel listing

**Files:**
- Modify: `ytdlman/downloader.py`
- Test: `tests/test_downloader.py`

**Interfaces:**
- Consumes: existing `PlaylistEntry`, `TrackFiles`, `DownloadError`, `parse_flat_playlist`, `run_command`.
- Produces:
  - `@dataclass Throttle(sleep_interval: int = 0, max_sleep_interval: int = 0, limit_rate: str = "")`
  - `class RateLimitError(DownloadError)`
  - `_is_rate_limited(text: str) -> bool`
  - `build_entries_command(ytdlp, url, cookies, *, throttle: Throttle = Throttle())` — adds `--sleep-requests 1` when `sleep_interval > 0`.
  - `build_download_command(..., throttle: Throttle = Throttle())` — adds `--sleep-interval/--max-sleep-interval/--sleep-requests` when `sleep_interval > 0` and `--limit-rate` when `limit_rate` non-empty.
  - `list_playlist_entries(ytdlp, url, cookies, *, throttle: Throttle = Throttle(), runner=run_command)` — raises `RateLimitError` when stderr indicates 429, else `DownloadError`.
  - `download_track(entry, dest_dir, *, ytdlp, ffmpeg_dir, bin_dir, cookies, audio_quality, throttle: Throttle = Throttle(), runner=run_command)` — same 429 distinction.

- [ ] **Step 1: Write the failing tests** — append to `tests/test_downloader.py`

```python
import subprocess
from pathlib import Path
import pytest
from ytdlman.downloader import (
    Throttle, RateLimitError, _is_rate_limited,
    build_entries_command, build_download_command,
    list_playlist_entries, download_track, PlaylistEntry,
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_downloader.py -k "throttle or ratelimit or rate_limited or channel or entries_command_adds" -v`
Expected: FAIL — `ImportError: cannot import name 'Throttle'`

- [ ] **Step 3: Add `Throttle`, `RateLimitError`, `_is_rate_limited`** — in `ytdlman/downloader.py`, after the existing `class DownloadError(Exception): pass`:

```python
class RateLimitError(DownloadError):
    """Raised when yt-dlp reports HTTP 429 (Too Many Requests)."""


@dataclass
class Throttle:
    sleep_interval: int = 0
    max_sleep_interval: int = 0
    limit_rate: str = ""


_RATE_LIMIT_MARKERS = ("http error 429", "too many requests", "429")


def _is_rate_limited(text: str) -> bool:
    low = (text or "").lower()
    return any(marker in low for marker in _RATE_LIMIT_MARKERS)


def _download_throttle_args(throttle: "Throttle") -> list[str]:
    args = []
    if throttle.sleep_interval > 0:
        args += [
            "--sleep-interval", str(throttle.sleep_interval),
            "--max-sleep-interval", str(max(throttle.max_sleep_interval, throttle.sleep_interval)),
            "--sleep-requests", "1",
        ]
    if throttle.limit_rate:
        args += ["--limit-rate", throttle.limit_rate]
    return args
```

(`dataclass` is already imported at the top of `downloader.py`.)

- [ ] **Step 4: Thread throttle into the command builders** — replace `build_entries_command` and `build_download_command` with:

```python
def build_entries_command(ytdlp: Path, url: str, cookies: Path | None, *,
                          throttle: Throttle = Throttle()) -> list[str]:
    cmd = [str(ytdlp), "--flat-playlist", "--no-warnings",
           "--print", "%(id)s\t%(title)s"]
    if throttle.sleep_interval > 0:
        cmd += ["--sleep-requests", "1"]
    if cookies and Path(cookies).exists():
        cmd += ["--cookies", str(cookies)]
    cmd.append(url)
    return cmd


def build_download_command(*, ytdlp: Path, video_id: str, out_template: str,
                           audio_quality: str, ffmpeg_dir: Path,
                           cookies: Path | None,
                           throttle: Throttle = Throttle()) -> list[str]:
    cmd = [
        str(ytdlp),
        "-x", "--audio-format", "mp3", "--audio-quality", f"{audio_quality}K",
        "--no-playlist", "--no-warnings",
        "--write-info-json", "--write-thumbnail", "--convert-thumbnails", "jpg",
        "--ffmpeg-location", str(ffmpeg_dir),
        "-o", out_template,
    ]
    cmd += _download_throttle_args(throttle)
    if cookies and Path(cookies).exists():
        cmd += ["--cookies", str(cookies)]
    cmd.append(f"https://www.youtube.com/watch?v={video_id}")
    return cmd
```

- [ ] **Step 5: Add 429 distinction to the runners** — replace `list_playlist_entries` and the failure check in `download_track`:

```python
def list_playlist_entries(ytdlp: Path, url: str, cookies: Path | None, *,
                          throttle: Throttle = Throttle(),
                          runner=run_command) -> list[PlaylistEntry]:
    cmd = build_entries_command(ytdlp, url, cookies, throttle=throttle)
    result = runner(cmd, env=None)
    if result.returncode != 0:
        if _is_rate_limited(result.stderr):
            raise RateLimitError(
                "YouTube ogranicza pobieranie (429) podczas listowania. Szczegóły w logu.")
        raise DownloadError(
            f"Nie udało się pobrać listy (kod {result.returncode}). Szczegóły w logu.")
    return parse_flat_playlist(result.stdout)


def download_track(entry: PlaylistEntry, dest_dir: Path, *, ytdlp: Path,
                   ffmpeg_dir: Path, bin_dir: Path, cookies: Path | None,
                   audio_quality: str, throttle: Throttle = Throttle(),
                   runner=run_command) -> TrackFiles:
    dest_dir.mkdir(parents=True, exist_ok=True)
    out_template = str(dest_dir / "%(id)s.%(ext)s")
    cmd = build_download_command(
        ytdlp=ytdlp, video_id=entry.video_id, out_template=out_template,
        audio_quality=audio_quality, ffmpeg_dir=ffmpeg_dir, cookies=cookies,
        throttle=throttle)
    result = runner(cmd, env=download_env(bin_dir))
    audio = dest_dir / f"{entry.video_id}.mp3"
    if result.returncode != 0 or not audio.exists():
        if _is_rate_limited(result.stderr):
            raise RateLimitError(
                f"YouTube ogranicza pobieranie (429) przy '{entry.title}'. Szczegóły w logu.")
        raise DownloadError(
            f"Pobieranie '{entry.title}' nie powiodło się "
            f"(kod {result.returncode}). Szczegóły w logu.")
    info = dest_dir / f"{entry.video_id}.info.json"
    thumb = dest_dir / f"{entry.video_id}.jpg"
    return TrackFiles(
        audio=audio,
        info_json=info if info.exists() else None,
        thumbnail=thumb if thumb.exists() else None,
    )
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_downloader.py -v`
Expected: PASS (existing downloader tests still green + new throttle/429/channel tests)

- [ ] **Step 7: Commit**

```bash
git add ytdlman/downloader.py tests/test_downloader.py
git commit -m "feat: throttle flags + 429 detection in yt-dlp commands; channel listing test"
```

---

### Task 3: Sync threads throttle + aborts on 429

**Files:**
- Modify: `ytdlman/sync.py`
- Test: `tests/test_sync.py`

**Interfaces:**
- Consumes: `config.Settings` (the new throttle fields), `downloader.Throttle`, `downloader.RateLimitError`, existing `download_track`/`list_playlist_entries`.
- Produces: `sync_playlist` builds a `Throttle` from `config.settings` for its default providers; on `RateLimitError` it rolls back the reserved `next_track_number`, does NOT add a `failed` track, and re-raises (aborting `sync_playlist` and `sync_all`).

- [ ] **Step 1: Write the failing tests** — append to `tests/test_sync.py`

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_sync.py -k ratelimit -v`
Expected: FAIL — current generic `except Exception` marks the track `failed` and continues, so `RateLimitError` is not raised and `next_track_number` is not rolled back.

- [ ] **Step 3: Update imports and default providers** — in `ytdlman/sync.py`, change the downloader import to include `Throttle` and `RateLimitError`:

```python
from .downloader import (
    PlaylistEntry, TrackFiles, DownloadError, RateLimitError, Throttle,
    list_playlist_entries, download_track,
)
```

In `sync_playlist`, where the default providers are created, build a `Throttle` from settings and pass it:

```python
    throttle = Throttle(
        sleep_interval=config.settings.sleep_interval,
        max_sleep_interval=config.settings.max_sleep_interval,
        limit_rate=config.settings.limit_rate,
    )
    if entries_provider is None:
        entries_provider = lambda url: list_playlist_entries(
            ytdlp, url, cookies, throttle=throttle)
    if track_downloader is None:
        track_downloader = lambda entry, dest, number: download_track(
            entry, dest, ytdlp=ytdlp, ffmpeg_dir=ffmpeg_dir, bin_dir=bin_dir,
            cookies=cookies, audio_quality=config.settings.audio_quality,
            throttle=throttle)
```

- [ ] **Step 4: Add the `RateLimitError` branch in the per-track loop** — in `sync_playlist`, the loop body currently is:

```python
        number = reserve_track_number(playlist)
        save()  # persist reserved number before doing work
        try:
            files = track_downloader(entry, dest, number)
            ...success path...
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
```

Insert a `RateLimitError` handler BEFORE the generic `except Exception` (so the rate-limit case is caught first):

```python
        except RateLimitError:
            # 429: abort the whole sync. Do not mark the track failed; roll back
            # the reserved number so numbering stays gap-free, then re-raise.
            playlist.next_track_number -= 1
            log.warning("[yellow]429[/yellow] — przerywam synchronizację playlisty.")
            raise
        except Exception as exc:
            upsert_track(playlist, Track(
                video_id=entry.video_id, track_number=number,
                title=clean_title(entry.title), status=STATUS_FAILED,
                error=str(exc)))
            failed += 1
            log.error("[red]Błąd[/red] '%s': %s", entry.title, exc)
        finally:
            save()  # persist outcome after every track
```

Note: the `finally: save()` still runs on the `RateLimitError` path (persisting the rolled-back `next_track_number`) before the exception propagates — which is what we want.

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_sync.py -v`
Expected: PASS (existing sync tests still green + the two new RateLimitError tests)

- [ ] **Step 6: Run the full suite**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS (all prior tests across the project remain green)

- [ ] **Step 7: Commit**

```bash
git add ytdlman/sync.py tests/test_sync.py
git commit -m "feat: sync threads throttle and aborts cleanly on 429 (with number rollback)"
```

---

### Task 4: UI pause + editable settings + app 429 handling

**Files:**
- Modify: `ytdlman/ui.py`, `ytdlman/app.py`

**Interfaces:**
- Consumes: `config.validate_throttle`, `downloader.RateLimitError`, existing `ui` helpers and `app` menu loop.
- Produces:
  - `ui.pause(message="Naciśnij Enter, aby wrócić do menu...") -> None`
  - `ui.edit_settings(settings) -> bool` — interactively edits `audio_quality`, `sleep_interval`, `max_sleep_interval`, `limit_rate`, `auto_check_updates` in place (validating throttle via `validate_throttle`, re-prompting on error); returns True if applied, False if cancelled.
  - `app`: `sync_all`/`sync_one` wrapped so `RateLimitError` shows a message + `pause()` and returns to the menu; the `settings` menu calls `ui.edit_settings` and saves.

  This task is interactive/IO — verified by import smoke-test + full suite, not new unit tests.

- [ ] **Step 1: Add `pause` and `edit_settings` to `ytdlman/ui.py`** — add `from .config import validate_throttle` to the imports at the top, then add these functions near the other helpers:

```python
def pause(message: str = "Naciśnij Enter, aby wrócić do menu...") -> None:
    try:
        questionary.press_any_key_to_continue(message).ask()
    except Exception:
        try:
            input(message)
        except EOFError:
            pass


def edit_settings(settings) -> bool:
    """Edit settings in place. Returns True if applied, False if cancelled."""
    audio_quality = questionary.text(
        "Jakość audio (np. 320):", default=settings.audio_quality).ask()
    if audio_quality is None:
        return False
    while True:
        sleep_raw = questionary.text(
            "Przerwa min (s):", default=str(settings.sleep_interval)).ask()
        if sleep_raw is None:
            return False
        max_raw = questionary.text(
            "Przerwa max (s):", default=str(settings.max_sleep_interval)).ask()
        if max_raw is None:
            return False
        limit_raw = questionary.text(
            "Limit pasma (puste / 500K / 1M):", default=settings.limit_rate).ask()
        if limit_raw is None:
            return False
        try:
            sleep_interval, max_sleep_interval, limit_rate = validate_throttle(
                sleep_raw, max_raw, limit_raw)
            break
        except ValueError as exc:
            error(str(exc))
    auto = questionary.confirm(
        "Auto-sprawdzanie aktualizacji aplikacji?",
        default=settings.auto_check_updates).ask()
    if auto is None:
        return False
    settings.audio_quality = audio_quality.strip() or settings.audio_quality
    settings.sleep_interval = sleep_interval
    settings.max_sleep_interval = max_sleep_interval
    settings.limit_rate = limit_rate
    settings.auto_check_updates = bool(auto)
    return True
```

- [ ] **Step 2: Wire 429 handling and editable settings into `ytdlman/app.py`** — add the import near the top:

```python
from .downloader import RateLimitError
```

Replace the `sync_all` and `sync_one` menu branches with rate-limit-aware versions:

```python
            elif choice == "sync_all":
                try:
                    results = sync_all(config, **sync_kwargs)
                    total = sum(r.downloaded for r in results.values())
                    fails = sum(r.failed for r in results.values())
                    ui.success(f"Gotowe. Pobrano {total}, błędów {fails}.")
                except RateLimitError:
                    ui.warn("YouTube ogranicza pobieranie (błąd 429). Przerwano "
                            "synchronizację. Zwiększ przerwy w Ustawieniach i "
                            "spróbuj później.")
                    ui.pause()
            elif choice == "sync_one":
                pl = ui.select_playlist(config.playlists)
                if pl:
                    try:
                        r = sync_playlist(config, pl, **sync_kwargs)
                        ui.success(f"Gotowe. Pobrano {r.downloaded}, błędów {r.failed}.")
                    except RateLimitError:
                        ui.warn("YouTube ogranicza pobieranie (błąd 429). Przerwano "
                                "synchronizację. Zwiększ przerwy w Ustawieniach i "
                                "spróbuj później.")
                        ui.pause()
```

Replace the `settings` menu branch (currently a read-only `ui.info(...)`) with:

```python
            elif choice == "settings":
                if ui.edit_settings(config.settings):
                    save()
                    ui.success("Zapisano ustawienia.")
```

- [ ] **Step 3: Smoke-test imports**

Run: `YTDLMAN_HOME=$(mktemp -d) .venv/bin/python -c "import main; from ytdlman import app, ui; from ytdlman.config import validate_throttle; print('imports OK')"`
Expected: prints `imports OK`

- [ ] **Step 4: Smoke-test the rate-limit message path (non-interactive)**

Run:
```bash
YTDLMAN_HOME=$(mktemp -d) .venv/bin/python -c "
from ytdlman import ui
ui.warn('test 429 message')
ui.pause('(pause skipped in non-tty)')
print('pause OK')
"
```
Expected: prints the warning and `pause OK` without hanging (the `pause` fallback swallows EOF in a non-tty).

- [ ] **Step 5: Run the full suite**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS (all tests remain green)

- [ ] **Step 6: Commit**

```bash
git add ytdlman/ui.py ytdlman/app.py
git commit -m "feat: pause + editable settings; app stops to menu on 429"
```

---

## Self-Review Notes

- **Spec coverage:** channel = same flow (no new code; Task 2 channel-listing test documents it); throttle settings + defaults + backward compat (Task 1); yt-dlp flag mapping incl. `--sleep-requests 1` only when `sleep_interval>0` and independent `--limit-rate` (Task 2); validation incl. `max≥min` and `limit_rate` format (Task 1 `validate_throttle`); 429 detection markers → `RateLimitError` (Task 2); 429 abort + no-failed + number rollback + propagation (Task 3); `app` message + `pause()` + return to menu (Task 4); editable settings screen with `music_dir` left out (Task 4). All covered.
- **Placeholder scan:** none — every code step is complete.
- **Type consistency:** `Throttle` and `RateLimitError` defined in Task 2 and imported unchanged in Task 3; `validate_throttle` defined in Task 1, consumed in Task 4; throttle keyword threaded consistently through `build_*`/`list_playlist_entries`/`download_track`. Existing call sites keep working because every new parameter has a default (`Throttle()`), so prior tests stay green.
