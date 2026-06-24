"""Parse Google Chat event payloads."""

from dataclasses import dataclass


@dataclass
class ParsedEvent:
    """The fields we care about from a Google Chat event."""

    event_type: str
    space_name: str
    text: str
    thread_name: str | None
    thread_reply: bool  # True when the message is a reply inside an existing thread
    sender_type: str | None
    message_name: str | None


def parse_message_event(payload: dict) -> ParsedEvent:
    """Extract event type, space name, message text, thread name and sender type from a payload.

    Handles the Workspace Events shape (``{"message": {...}}`` with no top-level ``type``).
    Missing keys degrade to empty/``None`` values rather than raising, so callers can decide to
    silently ignore malformed or non-message events.
    """
    message = payload.get("message") or {}
    space = payload.get("space") or message.get("space") or {}
    thread = message.get("thread") or {}
    sender = message.get("sender") or {}
    return ParsedEvent(
        event_type=payload.get("type", ""),
        space_name=space.get("name", ""),
        text=message.get("text", ""),
        thread_name=thread.get("name") or None,
        thread_reply=bool(message.get("threadReply", False)),
        sender_type=sender.get("type"),
        message_name=message.get("name") or None,
    )
