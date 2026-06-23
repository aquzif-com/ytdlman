from ytdlman.cookies import inspect_cookies, CookiesInfo


def test_not_present(tmp_path):
    info = inspect_cookies(tmp_path / "cookies.txt")
    assert info == CookiesInfo(present=False, valid=False, entry_count=0, has_youtube=False)


def test_present_but_only_comments(tmp_path):
    p = tmp_path / "cookies.txt"
    p.write_text("# Netscape HTTP Cookie File\n# comment\n\n", encoding="utf-8")
    info = inspect_cookies(p)
    assert info.present is True
    assert info.valid is False
    assert info.entry_count == 0
    assert info.has_youtube is False


def test_present_valid_youtube_entry(tmp_path):
    p = tmp_path / "cookies.txt"
    p.write_text(
        "# Netscape HTTP Cookie File\n"
        ".youtube.com\tTRUE\t/\tTRUE\t1799999999\tLOGIN_INFO\tabc123\n",
        encoding="utf-8",
    )
    info = inspect_cookies(p)
    assert info.present is True
    assert info.valid is True
    assert info.entry_count == 1
    assert info.has_youtube is True


def test_present_valid_non_youtube_entry(tmp_path):
    p = tmp_path / "cookies.txt"
    p.write_text(
        ".example.com\tTRUE\t/\tFALSE\t0\tsession\txyz\n",
        encoding="utf-8",
    )
    info = inspect_cookies(p)
    assert info.valid is True
    assert info.entry_count == 1
    assert info.has_youtube is False


def test_httponly_prefixed_line_is_counted(tmp_path):
    p = tmp_path / "cookies.txt"
    p.write_text(
        "#HttpOnly_.youtube.com\tTRUE\t/\tTRUE\t1799999999\tSID\ttok\n",
        encoding="utf-8",
    )
    info = inspect_cookies(p)
    assert info.entry_count == 1
    assert info.valid is True
    assert info.has_youtube is True


def test_malformed_lines_ignored(tmp_path):
    p = tmp_path / "cookies.txt"
    p.write_text("not a cookie line\njust some text\n", encoding="utf-8")
    info = inspect_cookies(p)
    assert info.present is True
    assert info.valid is False
    assert info.entry_count == 0
