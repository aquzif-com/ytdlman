import re
from version import APP_VERSION
from ytdlman.clock import now_iso


def test_app_version_is_semver():
    assert re.fullmatch(r"\d+\.\d+\.\d+", APP_VERSION)


def test_now_iso_returns_iso_utc():
    value = now_iso()
    # e.g. 2026-06-23T12:34:56.789012+00:00
    assert re.match(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", value)
    assert value.endswith("+00:00")
