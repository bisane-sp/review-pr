"""Application logging: coloured console output + a rotating, datetime-stamped `.log` file."""

import logging
from datetime import datetime
from pathlib import Path

import colorlog

PROJECT_ROOT = Path(__file__).resolve().parents[2]
LOG_DIR = PROJECT_ROOT / "logs"
LOG_PREFIX = "review-pr"
MAX_BYTES = 10 * 1024 * 1024  # roll over once the active file exceeds 10 MB
RETENTION_DAYS = 7  # delete review-pr_*.log files older than this on startup

_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
_FILE_FORMAT = (
    "%(asctime)s.%(msecs)03d | %(levelname)-8s | pid:%(process)d | %(threadName)s | "
    "%(name)s | %(module)s:%(funcName)s:%(lineno)d | %(message)s"
)
_CONSOLE_FORMAT = (
    "%(asctime)s.%(msecs)03d | %(log_color)s%(levelname)-8s%(reset)s | pid:%(process)d | %(threadName)s | "
    "%(name)s | %(module)s:%(funcName)s:%(lineno)d | %(message)s"
)
_LEVEL_COLORS = {
    "DEBUG": "cyan",
    "INFO": "green",
    "WARNING": "yellow",
    "ERROR": "red",
    "CRITICAL": "bold_red",
}


class TimestampedSizeRotatingHandler(logging.FileHandler):
    """File handler that opens a fresh `review-pr_<datetime>.log` once the current file passes 10 MB."""

    def __init__(self) -> None:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        super().__init__(self._new_path(), encoding="utf-8")

    @staticmethod
    def _new_path() -> Path:
        """A unique log path stamped with the creation time, e.g. logs/review-pr_2026-06-24_14-30-00.log."""
        stamp = f"{datetime.now():%Y-%m-%d_%H-%M-%S}"
        path = LOG_DIR / f"{LOG_PREFIX}_{stamp}.log"
        counter = 1
        while path.exists():  # disambiguate rollovers that land in the same second
            path = LOG_DIR / f"{LOG_PREFIX}_{stamp}_{counter}.log"
            counter += 1
        return path

    def emit(self, record: logging.LogRecord) -> None:
        """Write the record, then start a new datetime-stamped file if the current one is over 10 MB."""
        super().emit(record)
        if self.stream and self.stream.tell() >= MAX_BYTES:
            self.close()
            self.baseFilename = str(self._new_path())
            self.stream = self._open()


def _prune_old_logs(keep: Path) -> None:
    """Delete ``review-pr_*.log`` files older than ``RETENTION_DAYS``, never the active ``keep`` file."""
    cutoff = datetime.now().timestamp() - RETENTION_DAYS * 86400
    for path in LOG_DIR.glob(f"{LOG_PREFIX}_*.log"):
        if path == keep:
            continue
        try:
            if path.stat().st_mtime < cutoff:
                path.unlink()
        except OSError:
            pass  # best-effort cleanup; skip files we can't stat or unlink


def setup_logging() -> None:
    """Configure the root logger: coloured console at INFO, full DEBUG log file. Idempotent."""
    root = logging.getLogger()
    if any(isinstance(h, TimestampedSizeRotatingHandler) for h in root.handlers):
        return  # already configured

    root.setLevel(logging.DEBUG)

    console = colorlog.StreamHandler()
    console.setLevel(logging.INFO)
    console.setFormatter(colorlog.ColoredFormatter(_CONSOLE_FORMAT, datefmt=_DATE_FORMAT, log_colors=_LEVEL_COLORS))

    file_handler = TimestampedSizeRotatingHandler()
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(_FILE_FORMAT, datefmt=_DATE_FORMAT))

    root.addHandler(console)
    root.addHandler(file_handler)

    try:
        _prune_old_logs(keep=Path(file_handler.baseFilename))
    except OSError:
        logging.getLogger(__name__).warning("Log retention prune failed", exc_info=True)
