import re
from pathlib import Path

from mutagen.id3 import ID3, TIT2, TPE1, TPE2, TALB, TRCK, TDRC, APIC

# Phrases that appear as (...) / [...] noise or "| ... " suffixes.
_NOISE_WORDS = (
    r"official\s+music\s+video", r"official\s+video", r"official\s+audio",
    r"official\s+lyric\s+video", r"lyric\s+video", r"lyrics?", r"visuali[sz]er",
    r"audio", r"video", r"hd", r"hq", r"4k", r"mv",
)
_NOISE_ALT = "|".join(_NOISE_WORDS)

TITLE_NOISE_PATTERNS = [
    rf"[\(\[]\s*(?:{_NOISE_ALT})\s*[\)\]]",   # (Official Video) / [Lyrics]
    rf"\|\s*(?:{_NOISE_ALT})\s*$",            # trailing | Official Video
]
_COMPILED = [re.compile(p, re.IGNORECASE) for p in TITLE_NOISE_PATTERNS]


def clean_title(raw: str) -> str:
    title = raw
    for pattern in _COMPILED:
        title = pattern.sub("", title)
    title = re.sub(r"\s{2,}", " ", title).strip()
    title = title.strip("-").strip()
    return title or raw.strip()


def extract_year(upload_date: str | None) -> str | None:
    if upload_date and len(upload_date) >= 4 and upload_date[:4].isdigit():
        return upload_date[:4]
    return None


def build_id3(*, artist: str, album: str, title: str, track_number: int,
              year: str | None, cover_jpeg: bytes | None) -> ID3:
    tags = ID3()
    tags.setall("TPE1", [TPE1(encoding=3, text=artist)])
    tags.setall("TPE2", [TPE2(encoding=3, text=artist)])
    tags.setall("TALB", [TALB(encoding=3, text=album)])
    tags.setall("TIT2", [TIT2(encoding=3, text=title)])
    tags.setall("TRCK", [TRCK(encoding=3, text=str(track_number))])
    if year:
        tags.setall("TDRC", [TDRC(encoding=3, text=year)])
    if cover_jpeg:
        tags.setall("APIC", [APIC(encoding=3, mime="image/jpeg", type=3,
                                  desc="Cover", data=cover_jpeg)])
    return tags


def write_tags(mp3_path: Path, *, artist: str, album: str, title: str,
               track_number: int, year: str | None, cover_jpeg: bytes | None) -> None:
    tags = build_id3(artist=artist, album=album, title=title,
                     track_number=track_number, year=year, cover_jpeg=cover_jpeg)
    tags.save(str(mp3_path))
