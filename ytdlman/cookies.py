from dataclasses import dataclass
from pathlib import Path

# Domain hints that indicate the cookies cover YouTube (auth often lives on
# google.com cookies too, so we treat those as YouTube-relevant).
_YOUTUBE_HINTS = ("youtube.com", "youtu.be", "google.com")

_HTTPONLY_PREFIX = "#HttpOnly_"


@dataclass
class CookiesInfo:
    present: bool      # file exists next to the app
    valid: bool        # looks like a usable Netscape cookie file (>= 1 cookie line)
    entry_count: int   # number of well-formed cookie lines
    has_youtube: bool  # at least one cookie for a YouTube/Google domain


def inspect_cookies(path: Path) -> CookiesInfo:
    """Best-effort, offline inspection of a Netscape-format cookies.txt.

    We cannot verify that the cookies actually work without contacting YouTube,
    so 'valid' only means the file parses as a cookie jar with at least one
    well-formed entry (7 tab-separated fields).
    """
    if not path.exists() or not path.is_file():
        return CookiesInfo(present=False, valid=False, entry_count=0, has_youtube=False)

    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return CookiesInfo(present=True, valid=False, entry_count=0, has_youtube=False)

    entry_count = 0
    has_youtube = False
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        # Comments start with '#', except the '#HttpOnly_' domain prefix which
        # marks a real cookie line that yt-dlp/curl honour.
        if stripped.startswith("#") and not stripped.startswith(_HTTPONLY_PREFIX):
            continue
        fields = line.split("\t")
        if len(fields) < 7:
            continue
        entry_count += 1
        domain = fields[0]
        if domain.startswith(_HTTPONLY_PREFIX):
            domain = domain[len(_HTTPONLY_PREFIX):]
        domain = domain.lower()
        if any(hint in domain for hint in _YOUTUBE_HINTS):
            has_youtube = True

    return CookiesInfo(present=True, valid=entry_count > 0,
                       entry_count=entry_count, has_youtube=has_youtube)
