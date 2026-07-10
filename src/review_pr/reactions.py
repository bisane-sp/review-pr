"""Add or remove an emoji reaction on a Chat message via the Chat REST API.

Incoming webhooks (used by ``notify.py``) can only post messages — they cannot manage reactions.
Reactions require an authenticated Chat API call, so this reuses the user OAuth credentials saved
by ``scripts/manage_subscription.py`` (``.keys/token.json``). Deleting a reaction needs the broad
``chat.messages.reactions`` scope (create-only is not enough); re-run the authorize flow if the
token was minted with a narrower scope.

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

# Must match the scopes the token was authorized with (see manage_subscription.py). The broad
# reactions scope (not the create-only one) is required to delete reactions.
SCOPES = [
    "https://www.googleapis.com/auth/chat.messages.readonly",
    "https://www.googleapis.com/auth/chat.messages.reactions",
]

_TIMEOUT = 10


def add_reaction(message_name: str, emoji: str) -> str | None:
    """React to ``message_name`` (e.g. ``spaces/X/messages/Y``) with the unicode ``emoji``.

    Returns the created reaction's resource name (``spaces/X/messages/Y/reactions/Z``) so it can
    later be passed to ``remove_reaction``, or ``None`` if the call failed.
    """
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
        return response.json().get("name")
    except Exception:
        logger.exception("Failed to add reaction %s to %s", emoji, message_name)
        return None


def remove_reaction(reaction_name: str) -> None:
    """Delete the reaction identified by ``reaction_name`` (``spaces/X/messages/Y/reactions/Z``)."""
    try:
        creds = Credentials.from_authorized_user_file(str(_TOKEN_FILE), SCOPES)
        if not creds.valid:
            creds.refresh(Request())
        response = requests.delete(
            f"https://chat.googleapis.com/v1/{reaction_name}",
            headers={"Authorization": f"Bearer {creds.token}"},
            timeout=_TIMEOUT,
        )
        response.raise_for_status()
    except Exception:
        logger.exception("Failed to remove reaction %s", reaction_name)
