"""Thread-safe, in-memory dedup guard for Pub/Sub at-least-once delivery.

Pub/Sub can deliver the same Chat message more than once, and the subscriber client dispatches the
callback on multiple threads. Without a guard, two deliveries of one message could both pass the
eligibility checks and approve/merge the PR twice. ``claim`` records each message id under a lock,
so only the first delivery proceeds and later ones are skipped.
"""

import threading
from collections import OrderedDict

# Bound the history so a long-running subscriber doesn't grow without limit; the oldest id drops out.
_MAX_REMEMBERED = 1000

_lock = threading.Lock()
_seen: "OrderedDict[str, None]" = OrderedDict()


def claim(message_name: str) -> bool:
    """Atomically record ``message_name``. Return True for the first caller, False if already seen."""
    with _lock:
        if message_name in _seen:
            return False
        _seen[message_name] = None
        if len(_seen) > _MAX_REMEMBERED:
            _seen.popitem(last=False)
        return True
