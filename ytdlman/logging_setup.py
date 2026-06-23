import logging
from datetime import datetime, timezone

from rich.logging import RichHandler

from . import paths

_LOGGER_NAME = "ytdlman"


def get_logger() -> logging.Logger:
    return logging.getLogger(_LOGGER_NAME)


def setup_logging(level: int = logging.DEBUG) -> logging.Logger:
    logger = get_logger()
    logger.setLevel(level)
    if logger.handlers:  # idempotent
        return logger

    logs = paths.logs_dir()
    logs.mkdir(parents=True, exist_ok=True)
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    file_handler = logging.FileHandler(logs / f"ytdlman_{date}.log", encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    )

    console = RichHandler(level=logging.INFO, show_time=False, show_path=False,
                          rich_tracebacks=False, markup=True)

    logger.addHandler(file_handler)
    logger.addHandler(console)
    logger.propagate = False
    return logger
