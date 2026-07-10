"""Manage Workspace Events subscriptions for Chat spaces (create / renew / delete / ensure).

A Workspace Events subscription is what makes EVERY message in a Chat space flow to the
`chat-events` Pub/Sub topic (a plain Chat app only receives @mentions/DMs). Chat message
subscriptions expire (max ~4h TTL when the payload includes the message resource), so they
must be renewed periodically — see `ensure`.

Credentials (with refresh token) are persisted to `.keys/token.json` so renew/ensure run
headless after the first browser sign-in. Uses the same OAuth client that created the
subscription (`.keys/oauth_client.json`).

The space defaults to GOOGLE_CHAT_SPACE_ID from .env (read via review_pr.config.settings); pass a
`spaces/...` argument only to override it.

Usage:
  poetry run python scripts/manage_subscription.py ensure                 # space from .env; renew, else create
  poetry run python scripts/manage_subscription.py create [spaces/XXXX]
  poetry run python scripts/manage_subscription.py renew  [spaces/XXXX]
  poetry run python scripts/manage_subscription.py delete subscriptions/XXXX
"""

import json
import sys
from pathlib import Path

import requests
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from review_pr.config import settings

PROJECT_ROOT = Path(__file__).resolve().parent.parent
KEYS = PROJECT_ROOT / ".keys"
CLIENT_SECRETS = KEYS / "oauth_client.json"
TOKEN_FILE = KEYS / "token.json"
# readonly: create/renew the Workspace Events subscription. reactions: let the bot add *and remove*
# reactions on messages (see src/review_pr/reactions.py). Re-authorize if the saved token predates this.
SCOPES = [
    "https://www.googleapis.com/auth/chat.messages.readonly",
    "https://www.googleapis.com/auth/chat.messages.reactions",
]
TOPIC = "projects/review-pr-500320/topics/chat-events"
BASE = "https://workspaceevents.googleapis.com/v1"


def _name_file(space: str) -> Path:
    return KEYS / f"subscription_{space.split('/')[-1]}.txt"


def get_creds() -> Credentials:
    creds = None
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRETS), SCOPES)
            creds = flow.run_local_server(port=0)
        TOKEN_FILE.write_text(creds.to_json())
    return creds


def _headers(creds: Credentials) -> dict:
    return {"Authorization": f"Bearer {creds.token}", "Content-Type": "application/json"}


def create(creds: Credentials, space: str) -> str:
    body = {
        "targetResource": f"//chat.googleapis.com/{space}",
        "eventTypes": ["google.workspace.chat.message.v1.created"],
        "notificationEndpoint": {"pubsubTopic": TOPIC},
        "payloadOptions": {"includeResource": True},
    }
    r = requests.post(f"{BASE}/subscriptions", headers=_headers(creds), data=json.dumps(body), timeout=30)
    r.raise_for_status()
    name = r.json()["response"]["name"]
    _name_file(space).write_text(name)
    print(f"created {name}")
    return name


def renew(creds: Credentials, name: str) -> None:
    r = requests.patch(
        f"{BASE}/{name}?updateMask=ttl", headers=_headers(creds), data=json.dumps({"ttl": "0s"}), timeout=30
    )
    r.raise_for_status()
    exp = r.json().get("response", {}).get("expireTime") or r.json().get("metadata", {})
    print(f"renewed {name} -> expire {exp}")


def delete(creds: Credentials, name: str) -> None:
    r = requests.delete(f"{BASE}/{name}", headers=_headers(creds), timeout=30)
    r.raise_for_status()
    print(f"deleted {name}")


def ensure(creds: Credentials, space: str) -> None:
    """Renew the stored subscription for the space; create one if missing/expired."""
    nf = _name_file(space)
    if nf.exists():
        name = nf.read_text().strip()
        try:
            renew(creds, name)
            return
        except requests.HTTPError as exc:
            print(f"renew failed ({exc}); recreating")
    create(creds, space)


def main() -> None:
    action = sys.argv[1]
    target = sys.argv[2] if len(sys.argv) > 2 else None
    creds = get_creds()
    if action == "create":
        create(creds, target or settings.google_chat_space_id)
    elif action == "renew":
        ref = target or settings.google_chat_space_id
        renew(creds, _name_file(ref).read_text().strip() if ref.startswith("spaces/") else ref)
    elif action == "delete":
        if not target:
            raise SystemExit("delete requires a subscriptions/... resource name")
        delete(creds, target)
    elif action == "ensure":
        ensure(creds, target or settings.google_chat_space_id)
    else:
        raise SystemExit(f"unknown action: {action}")


if __name__ == "__main__":
    main()
