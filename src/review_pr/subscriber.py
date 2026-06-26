"""Cloud Pub/Sub pull subscriber: receives Google Chat events and dispatches them."""

import fcntl
import json
import logging
import subprocess
import sys
import threading
import time
from pathlib import Path

from dotenv import load_dotenv
from google.cloud import pubsub_v1

from .config import settings
from .handler import handle_chat_event
from .logging_setup import setup_logging

setup_logging()
logger = logging.getLogger(__name__)

# The Workspace Events subscription expires (~4h TTL), so renew well inside that window.
RENEW_INTERVAL_SECONDS = 3 * 60 * 60
_RENEW_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "manage_subscription.py"

# Single-instance guard: only one subscriber may run against the subscription at a time. Two would let
# Pub/Sub split messages between them. flock is released by the kernel the moment its holder dies, so
# there is never a stale lock to clean up.
_LOCK_FILE = Path(__file__).resolve().parents[2] / "state" / "review-pr-bot.lock"
_lock_handle = None  # module-global so the fd (and thus the lock) lives for the process lifetime


def _acquire_singleton_lock() -> None:
    """Ensure only one subscriber runs. flock auto-releases on process death (no stale locks)."""
    global _lock_handle
    _LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    _lock_handle = _LOCK_FILE.open("w")
    try:
        fcntl.flock(_lock_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        logger.error(
            "Another review-pr-bot instance already holds %s — exiting to avoid duplicate "
            "subscribers on one Pub/Sub subscription.",
            _LOCK_FILE,
        )
        sys.exit(1)


def _renewal_loop() -> None:
    """Renew the Workspace Events subscription on start, then every RENEW_INTERVAL_SECONDS.

    Runs in a daemon thread alongside the Pub/Sub loop. Failures are logged, never raised —
    a failed renewal must not take the subscriber down.
    """
    while True:
        try:
            result = subprocess.run(
                [sys.executable, str(_RENEW_SCRIPT), "ensure"],
                capture_output=True,
                text=True,
                check=True,
            )
            logger.info("Renewed Workspace Events subscription: %s", result.stdout.strip())
        except subprocess.CalledProcessError as exc:
            logger.error(
                "Failed to renew Workspace Events subscription (exit %s): %s",
                exc.returncode,
                (exc.stderr or exc.stdout or "").strip(),
            )
        except Exception:
            logger.exception("Failed to renew Workspace Events subscription")
        time.sleep(RENEW_INTERVAL_SECONDS)


def _callback(message: "pubsub_v1.subscriber.message.Message") -> None:
    """Decode a Pub/Sub message into a Chat event and handle it. Always ack."""
    try:
        payload = json.loads(message.data)
        logger.debug("Raw Pub/Sub message: %s", payload)
        handle_chat_event(payload)
    except Exception:
        logger.exception("Failed to handle Pub/Sub message")
    finally:
        message.ack()


def run() -> None:
    """Subscribe to the configured subscription and block, processing messages."""
    _acquire_singleton_lock()
    # Export .env (e.g. GOOGLE_APPLICATION_CREDENTIALS) so the Pub/Sub client can read it.
    load_dotenv()
    threading.Thread(target=_renewal_loop, name="subscription-renewer", daemon=True).start()
    subscriber = pubsub_v1.SubscriberClient()
    future = subscriber.subscribe(settings.pubsub_subscription, callback=_callback)
    logger.info("Listening on %s", settings.pubsub_subscription)
    with subscriber:
        try:
            future.result()
        except KeyboardInterrupt:
            future.cancel()
            future.result()


if __name__ == "__main__":
    run()
