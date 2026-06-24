"""Thread-safe dedup guard for Pub/Sub at-least-once delivery, with persistent state.

Pub/Sub can deliver the same Chat message more than once, and the subscriber client dispatches the
callback on multiple threads. Without a guard, two deliveries of one message could both pass the
eligibility checks and approve/merge the PR twice. ``claim`` records each message id under a lock,
so only the first delivery proceeds and later ones are skipped.

State is persisted to a gitignored JSON file (``state/dedup.json``) so that a redelivery after a
process restart is still recognised and correctly rejected.
"""

import json
import os
import threading
from collections import OrderedDict
from pathlib import Path

# Bound the history so a long-running subscriber doesn't grow without limit; the oldest id drops out.
_MAX_REMEMBERED = 1000

# Persist the seen-set so a redelivery after a restart is still recognised. state/ is gitignored.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
_DEDUP_FILE = PROJECT_ROOT / "state" / "dedup.json"

_lock = threading.Lock()
_seen: "OrderedDict[str, None]" = OrderedDict()
_loaded = False


def _load() -> None:
    """Populate ``_seen`` from the dedup file once. A missing or corrupt file starts empty."""
    global _loaded
    try:
        raw = json.loads(_DEDUP_FILE.read_text(encoding="utf-8"))
        if isinstance(raw, list):
            for name in raw[-_MAX_REMEMBERED:]:
                _seen[name] = None
    except (OSError, json.JSONDecodeError):
        pass
    _loaded = True


def _save() -> None:
    """Atomically mirror ``_seen`` to the dedup file (temp file + ``os.replace``).

    Any ``OSError`` propagates by design — unlike ``_load`` it is not swallowed, so a failure to
    persist surfaces to the caller rather than silently losing dedup state.
    """
    _DEDUP_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = _DEDUP_FILE.with_name(_DEDUP_FILE.name + ".tmp")
    tmp.write_text(json.dumps(list(_seen)), encoding="utf-8")
    os.replace(tmp, _DEDUP_FILE)


def claim(message_name: str) -> bool:
    """Atomically record ``message_name``. Return True for the first caller, False if already seen."""
    with _lock:
        if not _loaded:
            _load()
        if message_name in _seen:
            return False
        _seen[message_name] = None
        if len(_seen) > _MAX_REMEMBERED:
            _seen.popitem(last=False)
        _save()
        return True
