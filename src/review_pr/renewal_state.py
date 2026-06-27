"""Persist the time of the last Workspace Events subscription renewal.

The subscription has a ~4h TTL and is renewed from a daemon thread in ``subscriber.py``. Recording the
last successful renewal to a gitignored JSON file (``state/last_renewal.json``) lets the renewal loop
decide whether a renewal is actually due based on elapsed wall-clock time — surviving process restarts
instead of resetting an in-memory timer each time the bot starts.
"""

import json
import logging
import os
import threading
from pathlib import Path

logger = logging.getLogger(__name__)

# Persist the last-renewal time so a restart doesn't lose track of when we last renewed. state/ is
# gitignored.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
_FILE = PROJECT_ROOT / "state" / "last_renewal.json"

_lock = threading.Lock()


def load_last_renewal() -> float | None:
    """Return the epoch-seconds timestamp of the last renewal, or None if missing/corrupt."""
    with _lock:
        try:
            raw = json.loads(_FILE.read_text(encoding="utf-8"))
            ts = raw.get("last_renewal")
            return float(ts) if ts is not None else None
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            return None


def record_renewal(ts: float) -> None:
    """Atomically persist ``ts`` as the last-renewal time (temp file + ``os.replace``).

    Best-effort: an ``OSError`` is logged and swallowed, never raised — a persistence failure must not
    crash the renewal loop. The worst case is that a restart re-renews once unnecessarily.
    """
    with _lock:
        try:
            _FILE.parent.mkdir(parents=True, exist_ok=True)
            tmp = _FILE.with_name(_FILE.name + ".tmp")
            tmp.write_text(json.dumps({"last_renewal": ts}), encoding="utf-8")
            os.replace(tmp, _FILE)
        except OSError:
            logger.warning("Failed to persist renewal state to %s", _FILE, exc_info=True)


def should_renew(threshold_seconds: float, now: float) -> bool:
    """Return True if no renewal is recorded or the last one is at least ``threshold_seconds`` old."""
    last = load_last_renewal()
    return last is None or now - last >= threshold_seconds
