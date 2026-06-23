import logging
from ytdlman.logging_setup import setup_logging, get_logger


def test_setup_creates_log_file_under_app_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("YTDLMAN_HOME", str(tmp_path))
    logger = setup_logging()
    logger.info("hello")
    logger.debug("details")
    for h in logger.handlers:
        h.flush()
    logs = list((tmp_path / "logs").glob("ytdlman_*.log"))
    assert len(logs) == 1
    assert "details" in logs[0].read_text(encoding="utf-8")


def test_setup_is_idempotent(monkeypatch, tmp_path):
    monkeypatch.setenv("YTDLMAN_HOME", str(tmp_path))
    setup_logging()
    count = len(get_logger().handlers)
    setup_logging()
    assert len(get_logger().handlers) == count
