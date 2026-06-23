# Linux Build + Cross-Platform Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the YTDLMAN console app fully functional on Linux x86_64 alongside Windows — platform-aware paths, dependency bootstrap, and self-update — and add a CI job that builds a `ytdlman-linux` binary and attaches it to the same release as `ytdlman.exe`.

**Architecture:** A single `platform_target` module is the one source of truth for OS detection (overridable via `YTDLMAN_PLATFORM` for tests, like `YTDLMAN_HOME`). `paths`, `bootstrap`, and `updater` consult it to pick `.exe`-vs-no-suffix binary names, Windows-vs-Linux download URLs and archive formats, and the right release asset. A second CI job on `ubuntu-latest` builds the Linux binary.

**Tech Stack:** Python 3.12, existing `ytdlman` package, stdlib `tarfile`/`zipfile`, `pytest`, PyInstaller, GitHub Actions. No new third-party dependencies.

## Global Constraints

- Production targets: **Windows + Linux x86_64**. macOS is dev/test only (treated as "linux" in code; real bootstrap there runs only in tests with mocked `fetch`). x86_64 only — no ARM.
- Platform detection lives in `ytdlman/platform_target.py`: `target_os() -> "windows"|"linux"` honors env `YTDLMAN_PLATFORM` else autodetects from `sys.platform` (`win*` → windows, else linux); `is_windows()`, `exe_suffix()` (`.exe` / `""`), `make_executable(path)` (chmod 0o755 on non-Windows, no-op on Windows or missing file).
- Binary names by platform: Windows `yt-dlp.exe`/`ffmpeg.exe`/`ffprobe.exe`/`deno.exe`; Linux `yt-dlp`/`ffmpeg`/`ffprobe`/`deno` (yt-dlp lives next to the app; ffmpeg/ffprobe/deno under `bin/`).
- Linux dependency sources: yt-dlp asset `yt-dlp_linux` (saved as `yt-dlp`); ffmpeg `https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz` (`.tar.xz`, extract `ffmpeg`+`ffprobe`); Deno `deno-x86_64-unknown-linux-gnu.zip`. All downloaded binaries get `make_executable`.
- Release assets: `ytdlman.exe` (Windows, unchanged) + `ytdlman-linux` (Linux). Self-update picks the asset for the running platform.
- Existing Windows behavior must stay identical (existing tests pinned to `YTDLMAN_PLATFORM=windows` stay green); every change is additive/conditional.
- All user-facing text is Polish (intentional).
- Out of scope: ARM, macOS as a target, web UI, bumping GitHub Action versions (Node 20 warning).

---

## File Structure

```
ytdlman/platform_target.py   # NEW: target_os/is_windows/exe_suffix/make_executable
ytdlman/paths.py             # binary names use exe_suffix()
ytdlman/bootstrap.py         # per-platform URLs, tar.xz extraction, chmod
ytdlman/updater.py           # per-platform release asset + chmod after swap
.github/workflows/release.yml# + build-linux job (ubuntu-latest)
tests/test_platform_target.py# NEW
tests/test_paths.py          # existing path tests made platform-aware
tests/test_bootstrap.py      # existing tests pinned to windows; new linux tests
tests/test_updater.py        # + release_asset_url + chmod-after-swap
```

---

### Task 1: platform_target module

**Files:**
- Create: `ytdlman/platform_target.py`, `tests/test_platform_target.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `target_os() -> str` — `"windows"` or `"linux"`; env `YTDLMAN_PLATFORM` overrides; else `"windows"` if `sys.platform` starts with `win`, else `"linux"`.
  - `is_windows() -> bool`
  - `exe_suffix() -> str` — `".exe"` on Windows, `""` otherwise.
  - `make_executable(path: Path) -> None` — on non-Windows and when the file exists, `chmod(0o755)`; otherwise no-op.

- [ ] **Step 1: Write the failing tests** in `tests/test_platform_target.py`

```python
import os
from pathlib import Path
import ytdlman.platform_target as pt


def test_target_os_honors_env_override(monkeypatch):
    monkeypatch.setenv("YTDLMAN_PLATFORM", "windows")
    assert pt.target_os() == "windows"
    assert pt.is_windows() is True
    assert pt.exe_suffix() == ".exe"
    monkeypatch.setenv("YTDLMAN_PLATFORM", "linux")
    assert pt.target_os() == "linux"
    assert pt.is_windows() is False
    assert pt.exe_suffix() == ""


def test_target_os_autodetects_from_sys_platform(monkeypatch):
    monkeypatch.delenv("YTDLMAN_PLATFORM", raising=False)
    monkeypatch.setattr(pt.sys, "platform", "win32")
    assert pt.target_os() == "windows"
    monkeypatch.setattr(pt.sys, "platform", "linux")
    assert pt.target_os() == "linux"
    monkeypatch.setattr(pt.sys, "platform", "darwin")
    assert pt.target_os() == "linux"  # macOS treated as linux for code paths


def test_make_executable_sets_bit_on_linux(monkeypatch, tmp_path):
    monkeypatch.setenv("YTDLMAN_PLATFORM", "linux")
    f = tmp_path / "bin"
    f.write_bytes(b"x")
    pt.make_executable(f)
    assert os.access(f, os.X_OK)


def test_make_executable_noop_on_windows(monkeypatch, tmp_path):
    monkeypatch.setenv("YTDLMAN_PLATFORM", "windows")
    f = tmp_path / "bin"
    f.write_bytes(b"x")
    pt.make_executable(f)  # must not raise


def test_make_executable_missing_file_noop(monkeypatch, tmp_path):
    monkeypatch.setenv("YTDLMAN_PLATFORM", "linux")
    pt.make_executable(tmp_path / "nope")  # must not raise
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_platform_target.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ytdlman.platform_target'`

- [ ] **Step 3: Create `ytdlman/platform_target.py`**

```python
import os
import sys
from pathlib import Path


def target_os() -> str:
    """Return the runtime target: "windows" or "linux".

    YTDLMAN_PLATFORM overrides (for tests); otherwise autodetect from
    sys.platform. macOS (dev/test only) is treated as "linux".
    """
    override = os.environ.get("YTDLMAN_PLATFORM")
    if override:
        return override
    return "windows" if sys.platform.startswith("win") else "linux"


def is_windows() -> bool:
    return target_os() == "windows"


def exe_suffix() -> str:
    return ".exe" if is_windows() else ""


def make_executable(path: Path) -> None:
    """Mark a downloaded binary executable on non-Windows; no-op otherwise."""
    if is_windows() or not path.exists():
        return
    path.chmod(0o755)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_platform_target.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add ytdlman/platform_target.py tests/test_platform_target.py
git commit -m "feat: platform_target module (OS detection + make_executable)"
```

---

### Task 2: Platform-aware paths

**Files:**
- Modify: `ytdlman/paths.py`
- Test: `tests/test_paths.py`, `tests/test_bootstrap.py`

**Interfaces:**
- Consumes: `platform_target.exe_suffix`.
- Produces: `ytdlp_path`/`ffmpeg_path`/`ffprobe_path`/`deno_path` return names with the platform suffix (`.exe` on Windows, none on Linux). Other path functions unchanged.

- [ ] **Step 1: Update the existing path test to be platform-aware** — in `tests/test_paths.py`, REPLACE `test_derived_paths_live_under_app_dir` with two platform-pinned tests:

```python
def test_derived_paths_windows(monkeypatch, tmp_path):
    monkeypatch.setenv("YTDLMAN_HOME", str(tmp_path))
    monkeypatch.setenv("YTDLMAN_PLATFORM", "windows")
    assert paths.bin_dir() == tmp_path / "bin"
    assert paths.logs_dir() == tmp_path / "logs"
    assert paths.config_path() == tmp_path / "config.json"
    assert paths.cookies_path() == tmp_path / "cookies.txt"
    assert paths.ytdlp_path() == tmp_path / "yt-dlp.exe"
    assert paths.ffmpeg_path() == tmp_path / "bin" / "ffmpeg.exe"
    assert paths.ffprobe_path() == tmp_path / "bin" / "ffprobe.exe"
    assert paths.deno_path() == tmp_path / "bin" / "deno.exe"


def test_derived_paths_linux(monkeypatch, tmp_path):
    monkeypatch.setenv("YTDLMAN_HOME", str(tmp_path))
    monkeypatch.setenv("YTDLMAN_PLATFORM", "linux")
    assert paths.ytdlp_path() == tmp_path / "yt-dlp"
    assert paths.ffmpeg_path() == tmp_path / "bin" / "ffmpeg"
    assert paths.ffprobe_path() == tmp_path / "bin" / "ffprobe"
    assert paths.deno_path() == tmp_path / "bin" / "deno"
```

- [ ] **Step 2: Pin the existing bootstrap tests to Windows** so they keep asserting `.exe` after paths become platform-aware — in `tests/test_bootstrap.py`, add `monkeypatch.setenv("YTDLMAN_PLATFORM", "windows")` as the FIRST line of the body of BOTH `test_ensure_ytdlp_downloads_when_missing` and `test_current_status_reports_presence` (both already take `monkeypatch`). For example:

```python
def test_ensure_ytdlp_downloads_when_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("YTDLMAN_PLATFORM", "windows")
    monkeypatch.setenv("YTDLMAN_HOME", str(tmp_path))
    # ... rest unchanged ...
```

```python
def test_current_status_reports_presence(tmp_path, monkeypatch):
    monkeypatch.setenv("YTDLMAN_PLATFORM", "windows")
    monkeypatch.setenv("YTDLMAN_HOME", str(tmp_path))
    # ... rest unchanged ...
```

- [ ] **Step 3: Run the path tests to verify the new linux test fails**

Run: `.venv/bin/python -m pytest tests/test_paths.py -k "windows or linux" -v`
Expected: FAIL — `test_derived_paths_linux` fails because `ytdlp_path()` still returns `yt-dlp.exe`.

- [ ] **Step 4: Make the binary paths platform-aware** — in `ytdlman/paths.py`, add the import and rewrite the four binary-path functions:

Add after the existing imports (line 4 area):

```python
from . import platform_target
```

Replace `ytdlp_path`, `ffmpeg_path`, `ffprobe_path`, `deno_path` with:

```python
def ytdlp_path() -> Path:
    return app_dir() / f"yt-dlp{platform_target.exe_suffix()}"


def ffmpeg_dir() -> Path:
    return bin_dir()


def ffmpeg_path() -> Path:
    return bin_dir() / f"ffmpeg{platform_target.exe_suffix()}"


def ffprobe_path() -> Path:
    return bin_dir() / f"ffprobe{platform_target.exe_suffix()}"


def deno_path() -> Path:
    return bin_dir() / f"deno{platform_target.exe_suffix()}"
```

(Keep `ffmpeg_dir` where it already is; shown here only for context — do not duplicate it.)

- [ ] **Step 5: Run the path + bootstrap tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_paths.py tests/test_bootstrap.py -v`
Expected: PASS (platform-aware path tests pass; existing bootstrap tests still pass because they are pinned to windows)

- [ ] **Step 6: Run the full suite**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS (no regressions — note: `updater` tests run on the dev machine as "linux" but they pass explicit `download_url`/operate on fake files, so they are unaffected)

- [ ] **Step 7: Commit**

```bash
git add ytdlman/paths.py tests/test_paths.py tests/test_bootstrap.py
git commit -m "feat: platform-aware binary paths (.exe only on Windows)"
```

---

### Task 3: Platform-aware bootstrap (Linux URLs, tar.xz, chmod)

**Files:**
- Modify: `ytdlman/bootstrap.py`
- Test: `tests/test_bootstrap.py`

**Interfaces:**
- Consumes: `platform_target.target_os/exe_suffix/make_executable`, existing `paths`, `download_file`, `github_latest_tag`, `extract_members`.
- Produces:
  - Per-platform constants `YTDLP_ASSET`, `FFMPEG_URL`, `DENO_URL` (dicts keyed `"windows"`/`"linux"`).
  - `extract_tar_members(tar_path: Path, members_basenames: list[str], dest_dir: Path) -> list[Path]` — extracts matching basenames from a `.tar.xz`, flattening into `dest_dir`.
  - `ensure_ytdlp`/`ensure_ffmpeg`/`ensure_deno` choose source + archive handling by `target_os()` and `make_executable` the result. Signatures unchanged.

- [ ] **Step 1: Write the failing tests** — append to `tests/test_bootstrap.py`

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_bootstrap.py -k "tar_members or linux" -v`
Expected: FAIL — `extract_tar_members` does not exist; linux ensures still target `.exe`/Windows URLs.

- [ ] **Step 3: Add platform constants and the tar extractor** — in `ytdlman/bootstrap.py`, add `import tarfile` to the imports and `from . import paths, platform_target` (extend the existing `from . import paths`). Replace the URL constants block (lines 13-17) with:

```python
YTDLP_RELEASE_API = "https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest"
DENO_RELEASE_API = "https://api.github.com/repos/denoland/deno/releases/latest"

# Per-platform dependency sources (single place to change if a source moves).
YTDLP_ASSET = {"windows": "yt-dlp.exe", "linux": "yt-dlp_linux"}
FFMPEG_URL = {
    "windows": "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip",
    "linux": "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz",
}
DENO_URL = {
    "windows": "https://github.com/denoland/deno/releases/latest/download/deno-x86_64-pc-windows-msvc.zip",
    "linux": "https://github.com/denoland/deno/releases/latest/download/deno-x86_64-unknown-linux-gnu.zip",
}
```

Add `extract_tar_members` right after the existing `extract_members` function:

```python
def extract_tar_members(tar_path: Path, members_basenames: list[str], dest_dir: Path) -> list[Path]:
    dest_dir.mkdir(parents=True, exist_ok=True)
    wanted = set(members_basenames)
    extracted = []
    with tarfile.open(tar_path, "r:xz") as tf:
        for member in tf.getmembers():
            if not member.isfile():
                continue
            base = Path(member.name).name
            if base in wanted:
                src = tf.extractfile(member)
                if src is None:
                    continue
                target = dest_dir / base
                target.write_bytes(src.read())
                extracted.append(target)
    return extracted
```

- [ ] **Step 4: Make the three `ensure_*` functions platform-aware** — replace `ensure_ytdlp`, `ensure_ffmpeg`, and `ensure_deno` with:

```python
def ensure_ytdlp(config: Config, *, fetch=urlopen_fetch, save=lambda: None) -> DepStatus:
    target = paths.ytdlp_path()
    log = get_logger()
    if not target.exists():
        log.info("Pobieram yt-dlp...")
        try:
            tag = github_latest_tag("yt-dlp/yt-dlp", fetch=fetch)
            asset = YTDLP_ASSET[platform_target.target_os()]
            url = f"https://github.com/yt-dlp/yt-dlp/releases/download/{tag}/{asset}"
            download_file(url, target, fetch=fetch)
            platform_target.make_executable(target)
        except Exception as exc:
            raise BootstrapError(f"Nie udało się pobrać yt-dlp: {exc}") from exc
        _record(config, "yt-dlp", tag, save)
        return DepStatus("yt-dlp", True, tag)
    return DepStatus("yt-dlp", True, config.dependencies.get("yt-dlp", DependencyInfo()).version)


def ensure_ffmpeg(config: Config, *, fetch=urlopen_fetch, save=lambda: None) -> DepStatus:
    log = get_logger()
    if not paths.ffmpeg_path().exists():
        log.info("Pobieram ffmpeg...")
        os_name = platform_target.target_os()
        suffix = platform_target.exe_suffix()
        members = [f"ffmpeg{suffix}", f"ffprobe{suffix}"]
        if os_name == "windows":
            tmp = paths.bin_dir() / "_ffmpeg.zip"
            extractor = extract_members
        else:
            tmp = paths.bin_dir() / "_ffmpeg.tar.xz"
            extractor = extract_tar_members
        try:
            download_file(FFMPEG_URL[os_name], tmp, fetch=fetch)
            extractor(tmp, members, paths.bin_dir())
            platform_target.make_executable(paths.ffmpeg_path())
            platform_target.make_executable(paths.ffprobe_path())
        except Exception as exc:
            raise BootstrapError(f"Nie udało się pobrać ffmpeg: {exc}") from exc
        finally:
            if tmp.exists():
                tmp.unlink()
        _record(config, "ffmpeg", "bundled", save)
        return DepStatus("ffmpeg", True, "bundled")
    return DepStatus("ffmpeg", True, config.dependencies.get("ffmpeg", DependencyInfo()).version)


def ensure_deno(config: Config, *, fetch=urlopen_fetch, save=lambda: None) -> DepStatus:
    log = get_logger()
    if not paths.deno_path().exists():
        log.info("Pobieram Deno...")
        os_name = platform_target.target_os()
        tmp_zip = paths.bin_dir() / "_deno.zip"
        try:
            tag = github_latest_tag("denoland/deno", fetch=fetch)
            download_file(DENO_URL[os_name], tmp_zip, fetch=fetch)
            extract_members(tmp_zip, [f"deno{platform_target.exe_suffix()}"], paths.bin_dir())
            platform_target.make_executable(paths.deno_path())
        except Exception as exc:
            raise BootstrapError(f"Nie udało się pobrać Deno: {exc}") from exc
        finally:
            if tmp_zip.exists():
                tmp_zip.unlink()
        _record(config, "deno", tag, save)
        return DepStatus("deno", True, tag)
    return DepStatus("deno", True, config.dependencies.get("deno", DependencyInfo()).version)
```

- [ ] **Step 5: Run the bootstrap tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_bootstrap.py -v`
Expected: PASS (new linux/tar tests pass; the windows-pinned existing tests still pass)

- [ ] **Step 6: Run the full suite**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add ytdlman/bootstrap.py tests/test_bootstrap.py
git commit -m "feat: platform-aware dependency bootstrap (Linux URLs, tar.xz, chmod)"
```

---

### Task 4: Platform-aware self-update

**Files:**
- Modify: `ytdlman/updater.py`
- Test: `tests/test_updater.py`

**Interfaces:**
- Consumes: `platform_target.target_os/make_executable`, existing `github_latest_tag`/`download_file`/`urlopen_fetch`.
- Produces:
  - `ASSET = {"windows": "ytdlman.exe", "linux": "ytdlman-linux"}`
  - `release_asset_url() -> str` — latest-release download URL for the current platform's asset.
  - `apply_update(exe, *, fetch=urlopen_fetch, download_url=None)` — when `download_url is None`, uses `release_asset_url()`; after the swap, `make_executable(exe)`.

  Note: the helper is named `release_asset_url()` (not `download_url()`) to avoid clashing with the existing `download_url` keyword parameter of `apply_update`.

- [ ] **Step 1: Write the failing tests** — append to `tests/test_updater.py`

```python
import os


def test_release_asset_url_per_platform(monkeypatch):
    import ytdlman.updater as updater
    monkeypatch.setenv("YTDLMAN_PLATFORM", "windows")
    assert updater.release_asset_url().endswith("/ytdlman.exe")
    monkeypatch.setenv("YTDLMAN_PLATFORM", "linux")
    assert updater.release_asset_url().endswith("/ytdlman-linux")


def test_apply_update_marks_executable_on_linux(monkeypatch, tmp_path):
    import ytdlman.updater as updater
    monkeypatch.setenv("YTDLMAN_PLATFORM", "linux")
    exe = tmp_path / "ytdlman-linux"
    exe.write_bytes(b"OLD")
    result = updater.apply_update(exe, fetch=lambda url: b"NEW", download_url="http://x")
    assert result == exe
    assert exe.read_bytes() == b"NEW"
    assert os.access(exe, os.X_OK)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_updater.py -k "release_asset_url or marks_executable" -v`
Expected: FAIL — `release_asset_url` does not exist; no chmod after swap.

- [ ] **Step 3: Update `ytdlman/updater.py`** — change the imports and the URL handling.

Replace the import of bootstrap helpers and the `DOWNLOAD_URL` constant. The current top is:

```python
from .bootstrap import github_latest_tag, download_file, urlopen_fetch
from .logging_setup import get_logger

REPO = "aquzif-com/ytdlman"
DOWNLOAD_URL = f"https://github.com/{REPO}/releases/latest/download/ytdlman.exe"
```

Replace with:

```python
from .bootstrap import github_latest_tag, download_file, urlopen_fetch
from .logging_setup import get_logger
from .platform_target import target_os, make_executable

REPO = "aquzif-com/ytdlman"
ASSET = {"windows": "ytdlman.exe", "linux": "ytdlman-linux"}


def release_asset_url() -> str:
    return f"https://github.com/{REPO}/releases/latest/download/{ASSET[target_os()]}"
```

Change the `apply_update` signature and body. The current signature/body start:

```python
def apply_update(exe: Path, *, fetch=urlopen_fetch, download_url: str = DOWNLOAD_URL) -> Path:
```

Replace the signature with:

```python
def apply_update(exe: Path, *, fetch=urlopen_fetch, download_url: str | None = None) -> Path:
```

Immediately after the docstring inside `apply_update`, add the resolution of the default URL (before `new = _new_path(exe)`):

```python
    if download_url is None:
        download_url = release_asset_url()
```

And after the successful swap, before `log.info(...)`/`return exe`, add the chmod:

```python
    make_executable(exe)
```

So the tail of `apply_update` reads:

```python
    try:
        exe.replace(old)   # rename the running exe aside (allowed on Windows)
        new.replace(exe)   # move the freshly downloaded exe into place
    except OSError as exc:
        raise UpdateError(f"Nie udało się podmienić pliku aplikacji: {exc}") from exc

    make_executable(exe)
    log.info("Zaktualizowano aplikację: %s", exe)
    return exe
```

- [ ] **Step 4: Run the updater tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_updater.py -v`
Expected: PASS (existing updater tests + the two new platform tests; the existing `test_apply_update_swaps_in_new_exe` still passes — it passes an explicit `download_url`)

- [ ] **Step 5: Run the full suite**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add ytdlman/updater.py tests/test_updater.py
git commit -m "feat: platform-aware self-update asset (+chmod on Linux)"
```

---

### Task 5: CI — Linux build job

**Files:**
- Modify: `.github/workflows/release.yml`

**Interfaces:**
- Consumes: `version.APP_VERSION`, `requirements.txt`, `main.py`.
- Produces: a second job `build-linux` on `ubuntu-latest` producing `dist/ytdlman-linux` and attaching it to the same release on tag push. The existing Windows `build` job is unchanged.

- [ ] **Step 1: Add the `build-linux` job** — in `.github/workflows/release.yml`, append the following job under `jobs:` (sibling to the existing `build:` job, same indentation level as `build:`):

```yaml
  build-linux:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt pyinstaller pytest

      - name: Run tests
        run: python -m pytest -q

      - name: Verify tag matches APP_VERSION
        if: startsWith(github.ref, 'refs/tags/')
        run: |
          ver=$(python -c "from version import APP_VERSION; print(APP_VERSION)")
          tag="${GITHUB_REF_NAME#v}"
          if [ "$ver" != "$tag" ]; then
            echo "Tag $tag does not match APP_VERSION $ver"
            exit 1
          fi

      - name: Build linux binary
        run: pyinstaller --onefile --name ytdlman-linux main.py

      - name: Upload build artifact
        uses: actions/upload-artifact@v4
        with:
          name: ytdlman-linux
          path: dist/ytdlman-linux

      - name: Publish release
        if: startsWith(github.ref, 'refs/tags/')
        uses: softprops/action-gh-release@v2
        with:
          files: dist/ytdlman-linux
```

- [ ] **Step 2: Validate the YAML**

Run: `.venv/bin/python -c "import yaml; d=yaml.safe_load(open('.github/workflows/release.yml')); assert set(d['jobs'])=={'build','build-linux'}, d['jobs']; print('yaml OK; jobs:', list(d['jobs']))"`
Expected: prints `yaml OK; jobs: ['build', 'build-linux']`

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/release.yml
git commit -m "ci: add Linux (ubuntu-latest) build job to release workflow"
```

- [ ] **Step 4: Note for the controller (no action in this task)**

The Linux build is exercised for real only when the workflow runs on `ubuntu-latest` (tag push or `workflow_dispatch`). Both `build` and `build-linux` attach their asset to the same release via `softprops/action-gh-release` (it appends files, it does not overwrite the other job's asset).

---

## Self-Review Notes

- **Spec coverage:** platform_target with env override + autodetect + make_executable (Task 1); platform-aware paths with `.exe` only on Windows + existing tests made platform-aware (Task 2); bootstrap Linux URLs (yt-dlp_linux, johnvansickle tar.xz, deno linux zip), tar.xz extraction, chmod, per-platform selection (Task 3); updater per-platform release asset + chmod after swap (Task 4); CI second job building `ytdlman-linux` and attaching to the same release (Task 5). macOS-as-linux handled by `target_os()`. All covered.
- **Inter-task green:** Task 2 changes `paths` (which would otherwise break the `.exe`-assuming bootstrap tests on the dev machine), so Task 2 also pins those two existing bootstrap tests to `YTDLMAN_PLATFORM=windows`, keeping the full suite green at every task boundary.
- **Placeholder scan:** none — every code step is complete.
- **Type consistency:** `target_os()`/`exe_suffix()`/`make_executable()` defined in Task 1 and consumed unchanged in Tasks 2-4; bootstrap constants `YTDLP_ASSET`/`FFMPEG_URL`/`DENO_URL` keyed by the exact strings `target_os()` returns; `release_asset_url()` named to avoid the `download_url` param clash; all existing call sites keep working because changes are conditional on platform (Windows path identical to today).
