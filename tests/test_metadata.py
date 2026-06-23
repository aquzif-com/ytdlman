import pytest
from ytdlman.metadata import clean_title, extract_year, build_id3


@pytest.mark.parametrize("raw,expected", [
    ("Song Name (Official Video)", "Song Name"),
    ("Song Name [Official Music Video]", "Song Name"),
    ("Song Name (Lyrics)", "Song Name"),
    ("Song Name [Lyric Video]", "Song Name"),
    ("Song Name (Official Audio)", "Song Name"),
    ("Song Name (Visualizer)", "Song Name"),
    ("Song Name | Official Video", "Song Name"),
    ("Song Name (HD)", "Song Name"),
    ("Plain Song", "Plain Song"),
    ("Artist - Song (Live) (Official Video)", "Artist - Song (Live)"),
])
def test_clean_title(raw, expected):
    assert clean_title(raw) == expected


def test_extract_year():
    assert extract_year("20240115") == "2024"
    assert extract_year(None) is None
    assert extract_year("") is None


def test_build_id3_sets_expected_frames():
    tags = build_id3(artist="Me", album="Alb", title="T", track_number=3,
                     year="2024", cover_jpeg=b"\xff\xd8jpeg")
    assert tags["TPE1"].text == ["Me"]
    assert tags["TPE2"].text == ["Me"]
    assert tags["TALB"].text == ["Alb"]
    assert tags["TIT2"].text == ["T"]
    assert tags["TRCK"].text == ["3"]
    assert str(tags["TDRC"].text[0]) == "2024"
    apic = tags.getall("APIC")[0]
    assert apic.mime == "image/jpeg"
    assert apic.data == b"\xff\xd8jpeg"


def test_build_id3_omits_optional_when_absent():
    tags = build_id3(artist="Me", album="Alb", title="T", track_number=1,
                     year=None, cover_jpeg=None)
    assert tags.getall("APIC") == []
    assert tags.getall("TDRC") == []
