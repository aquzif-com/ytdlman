import io
import json
import zipfile
from dataclasses import dataclass
from pathlib import Path
from urllib.request import urlopen, Request

from . import paths
from .clock import now_iso
from .config import Config, DependencyInfo
from .logging_setup import get_logger

YTDLP_RELEASE_API = "https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest"
YTDLP_DOWNLOAD_URL = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe"
DENO_RELEASE_API = "https://api.github.com/repos/denoland/deno/releases/latest"
DENO_DOWNLOAD_URL = "https://github.com/denoland/deno/releases/latest/download/deno-x86_64-pc-windows-msvc.zip"
# Static FFmpeg build for Windows (changeable in one place if the source moves):
FFMPEG_DOWNLOAD_URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"


@dataclass
class DepStatus:
    name: str
    present: bool
    version: str | None


class BootstrapError(Exception):
    pass


def urlopen_fetch(url: str) -> bytes:
    req = Request(url, headers={"User-Agent": "ytdlman"})
    with urlopen(req, timeout=60) as resp:
        return resp.read()


def github_latest_tag(repo: str, *, fetch=urlopen_fetch) -> str:
    data = json.loads(fetch(f"https://api.github.com/repos/{repo}/releases/latest"))
    return data["tag_name"]


def download_file(url: str, dest: Path, *, fetch=urlopen_fetch, on_progress=None) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    data = fetch(url)
    dest.write_bytes(data)
    if on_progress:
        on_progress(len(data))


def extract_members(zip_path: Path, members_basenames: list[str], dest_dir: Path) -> list[Path]:
    dest_dir.mkdir(parents=True, exist_ok=True)
    wanted = set(members_basenames)
    extracted = []
    with zipfile.ZipFile(zip_path) as z:
        for info in z.infolist():
            base = Path(info.filename).name
            if base in wanted:
                target = dest_dir / base
                target.write_bytes(z.read(info))
                extracted.append(target)
    return extracted


def _record(config: Config, name: str, version: str | None, save) -> None:
    config.dependencies[name] = DependencyInfo(version=version, checked_at=now_iso())
    save()


def ensure_ytdlp(config: Config, *, fetch=urlopen_fetch, save=lambda: None) -> DepStatus:
    target = paths.ytdlp_path()
    log = get_logger()
    if not target.exists():
        log.info("Pobieram yt-dlp...")
        try:
            tag = github_latest_tag("yt-dlp/yt-dlp", fetch=fetch)
            url = f"https://github.com/yt-dlp/yt-dlp/releases/download/{tag}/yt-dlp.exe"
            download_file(url, target, fetch=fetch)
        except Exception as exc:
            raise BootstrapError(f"Nie udało się pobrać yt-dlp: {exc}") from exc
        _record(config, "yt-dlp", tag, save)
        return DepStatus("yt-dlp", True, tag)
    return DepStatus("yt-dlp", True, config.dependencies.get("yt-dlp", DependencyInfo()).version)


def ensure_ffmpeg(config: Config, *, fetch=urlopen_fetch, save=lambda: None) -> DepStatus:
    log = get_logger()
    if not paths.ffmpeg_path().exists():
        log.info("Pobieram ffmpeg...")
        tmp_zip = paths.bin_dir() / "_ffmpeg.zip"
        try:
            download_file(FFMPEG_DOWNLOAD_URL, tmp_zip, fetch=fetch)
            extract_members(tmp_zip, ["ffmpeg.exe", "ffprobe.exe"], paths.bin_dir())
        except Exception as exc:
            raise BootstrapError(f"Nie udało się pobrać ffmpeg: {exc}") from exc
        finally:
            if tmp_zip.exists():
                tmp_zip.unlink()
        _record(config, "ffmpeg", "bundled", save)
        return DepStatus("ffmpeg", True, "bundled")
    return DepStatus("ffmpeg", True, config.dependencies.get("ffmpeg", DependencyInfo()).version)


def ensure_deno(config: Config, *, fetch=urlopen_fetch, save=lambda: None) -> DepStatus:
    log = get_logger()
    if not paths.deno_path().exists():
        log.info("Pobieram Deno...")
        tmp_zip = paths.bin_dir() / "_deno.zip"
        try:
            tag = github_latest_tag("denoland/deno", fetch=fetch)
            download_file(DENO_DOWNLOAD_URL, tmp_zip, fetch=fetch)
            extract_members(tmp_zip, ["deno.exe"], paths.bin_dir())
        except Exception as exc:
            raise BootstrapError(f"Nie udało się pobrać Deno: {exc}") from exc
        finally:
            if tmp_zip.exists():
                tmp_zip.unlink()
        _record(config, "deno", tag, save)
        return DepStatus("deno", True, tag)
    return DepStatus("deno", True, config.dependencies.get("deno", DependencyInfo()).version)


def ensure_all(config: Config, *, save=lambda: None, fetch=urlopen_fetch) -> list[DepStatus]:
    return [
        ensure_ytdlp(config, fetch=fetch, save=save),
        ensure_ffmpeg(config, fetch=fetch, save=save),
        ensure_deno(config, fetch=fetch, save=save),
    ]


def current_status(config: Config) -> list[DepStatus]:
    checks = {
        "yt-dlp": paths.ytdlp_path(),
        "ffmpeg": paths.ffmpeg_path(),
        "deno": paths.deno_path(),
    }
    out = []
    for name, path in checks.items():
        info = config.dependencies.get(name, DependencyInfo())
        out.append(DepStatus(name, path.exists(), info.version))
    return out
