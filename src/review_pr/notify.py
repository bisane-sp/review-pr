"""Post messages back into the Google Chat space via the incoming webhook."""

import logging

import requests

from .config import settings

logger = logging.getLogger(__name__)

_TIMEOUT = 10


def post_message(text: str, thread_name: str | None = None) -> None:
    """Post ``text`` into the space, threaded under ``thread_name`` when provided.

    Failures are logged, not raised — a failed notification must not crash the subscriber.
    """
    payload: dict = {"text": text}
    params: dict = {}
    if thread_name:
        payload["thread"] = {"name": thread_name}
        params["messageReplyOption"] = "REPLY_MESSAGE_FALLBACK_TO_NEW_THREAD"

    try:
        response = requests.post(
            settings.google_chat_webhook_url,
            json=payload,
            params=params,
            timeout=_TIMEOUT,
        )
        response.raise_for_status()
    except requests.RequestException:
        logger.exception("Failed to post message to Google Chat")
