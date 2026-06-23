from datetime import datetime, timezone


def now_iso() -> str:
    """Current UTC time as ISO-8601. Single seam for tests to monkeypatch."""
    return datetime.now(timezone.utc).isoformat()
