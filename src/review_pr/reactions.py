"""Add an emoji reaction to a Chat message via the Chat REST API.

Incoming webhooks (used by ``notify.py``) can only post messages — they cannot create reactions.
Reactions require an authenticated Chat API call, so this reuses the user OAuth credentials saved
by ``scripts/manage_subscription.py`` (``.keys/token.json``). That token must include the
``chat.messages.reactions.create`` scope; re-run the authorize flow if it was minted read-only.

Failures are logged, not raised — a missing reaction must never crash the subscriber.
"""

import logging
from pathlib import Path

import requests
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

logger = logging.getLogger(__name__)

# token.json lives in the project's .keys/ (src/review_pr/reactions.py -> src -> project root).
_TOKEN_FILE = Path(__file__).resolve().parent.parent.parent / ".keys" / "token.json"

# Must match the scopes the token was authorized with (see manage_subscription.py).
SCOPES = [
    "https://www.googleapis.com/auth/chat.messages.readonly",
    "https://www.googleapis.com/auth/chat.messages.reactions.create",
]

_TIMEOUT = 10


def add_reaction(message_name: str, emoji: str) -> None:
    """React to ``message_name`` (e.g. ``spaces/X/messages/Y``) with the unicode ``emoji``."""
    try:
        creds = Credentials.from_authorized_user_file(str(_TOKEN_FILE), SCOPES)
        if not creds.valid:
            creds.refresh(Request())
        response = requests.post(
            f"https://chat.googleapis.com/v1/{message_name}/reactions",
            headers={"Authorization": f"Bearer {creds.token}"},
            json={"emoji": {"unicode": emoji}},
            timeout=_TIMEOUT,
        )
        response.raise_for_status()
    except Exception:
        logger.exception("Failed to add reaction %s to %s", emoji, message_name)
