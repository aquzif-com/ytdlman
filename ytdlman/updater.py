import sys
from dataclasses import dataclass
from pathlib import Path

from .bootstrap import github_latest_tag, download_file, urlopen_fetch
from .logging_setup import get_logger
from .platform_target import target_os, make_executable

REPO = "aquzif-com/ytdlman"
ASSET = {"windows": "ytdlman.exe", "linux": "ytdlman-linux"}


def release_asset_url() -> str:
    return f"https://github.com/{REPO}/releases/latest/download/{ASSET[target_os()]}"


class UpdateError(Exception):
    pass


@dataclass
class UpdateCheck:
    current: str
    latest: str | None
    available: bool


def parse_version(tag: str) -> tuple[int, ...]:
    cleaned = tag.strip().lstrip("vV")
    parts = []
    for piece in cleaned.split("."):
        digits = "".join(ch for ch in piece if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


def is_newer(latest: str, current: str) -> bool:
    return parse_version(latest) > parse_version(current)


def check_for_update(current_version: str, *, fetch=urlopen_fetch) -> UpdateCheck:
    try:
        latest = github_latest_tag(REPO, fetch=fetch)
    except Exception as exc:
        get_logger().warning("Nie udało się sprawdzić aktualizacji aplikacji: %s", exc)
        return UpdateCheck(current=current_version, latest=None, available=False)
    return UpdateCheck(current=current_version, latest=latest,
                       available=is_newer(latest, current_version))


def running_exe() -> Path | None:
    """Path to the running executable when frozen (PyInstaller), else None.

    Self-update only works on the built .exe; in dev mode there is nothing to
    replace.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve()
    return None


def _old_path(exe: Path) -> Path:
    return exe.with_name(exe.stem + ".old" + exe.suffix)


def _new_path(exe: Path) -> Path:
    return exe.with_name(exe.stem + ".new" + exe.suffix)


def cleanup_old_executable(exe: Path) -> None:
    """Remove the leftover .old executable from a previous update, if present."""
    old = _old_path(exe)
    try:
        if old.exists():
            old.unlink()
    except OSError as exc:
        get_logger().debug("Nie udało się usunąć starego pliku %s: %s", old, exc)


def apply_update(exe: Path, *, fetch=urlopen_fetch, download_url: str | None = None) -> Path:
    """Download the new exe and swap it into place. Returns the final exe path.

    Windows allows renaming a running exe but not overwriting it, so we
    download to a .new file, move the running exe aside to .old, then move the
    .new file into place. The caller must restart; the stale .old file is
    removed on the next launch via cleanup_old_executable().
    """
    if download_url is None:
        download_url = release_asset_url()
    log = get_logger()
    new = _new_path(exe)
    old = _old_path(exe)

    try:
        download_file(download_url, new, fetch=fetch)
    except Exception as exc:
        raise UpdateError(f"Nie udało się pobrać nowej wersji: {exc}") from exc

    if old.exists():
        try:
            old.unlink()
        except OSError:
            pass
    try:
        exe.replace(old)   # rename the running exe aside (allowed on Windows)
        new.replace(exe)   # move the freshly downloaded exe into place
    except OSError as exc:
        raise UpdateError(f"Nie udało się podmienić pliku aplikacji: {exc}") from exc

    make_executable(exe)
    log.info("Zaktualizowano aplikację: %s", exe)
    return exe
