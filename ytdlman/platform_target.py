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
