"""Cloud Pub/Sub pull subscriber: receives Google Chat events and dispatches them."""

import json
import logging

from dotenv import load_dotenv
from google.cloud import pubsub_v1

from .config import settings
from .handler import handle_chat_event
from .logging_setup import setup_logging

setup_logging()
logger = logging.getLogger(__name__)


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
    # Export .env (e.g. GOOGLE_APPLICATION_CREDENTIALS) so the Pub/Sub client can read it.
    load_dotenv()
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
