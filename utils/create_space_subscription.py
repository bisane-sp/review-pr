"""One-off: create a Workspace Events API subscription so ALL messages in the space
are published to the chat-events Pub/Sub topic.

Prereqs (see temp/workspace-events-all-messages-setup.md):
  - Google Workspace Events API enabled in the project
  - OAuth Desktop client downloaded (path in OAUTH_CLIENT_SECRETS)
  - The Chat push service account has Pub/Sub Publisher on the topic (already done)

Required settings (.env, read via review_pr.config.settings):
  - GOOGLE_CHAT_SPACE_ID   space resource name, e.g. "spaces/AAQA1u4..."
  - CHAT_EVENTS_TOPIC      Pub/Sub topic, e.g. "projects/PROJECT/topics/chat-events"
  - OAUTH_CLIENT_SECRETS   path to the OAuth Desktop client JSON

Run:
  poetry run python utils/create_space_subscription.py
"""

import json

import requests
from google_auth_oauthlib.flow import InstalledAppFlow

from review_pr.config import settings

SCOPES = ["https://www.googleapis.com/auth/chat.messages.readonly"]


def main() -> None:
    space_id = settings.google_chat_space_id
    topic = settings.chat_events_topic
    client_secrets = settings.oauth_client_secrets

    flow = InstalledAppFlow.from_client_secrets_file(client_secrets, SCOPES)
    # Opens a browser; sign in as a MEMBER of the space and consent.
    creds = flow.run_local_server(port=0)

    body = {
        "targetResource": f"//chat.googleapis.com/{space_id}",
        "eventTypes": ["google.workspace.chat.message.v1.created"],
        "notificationEndpoint": {"pubsubTopic": topic},
        "payloadOptions": {"includeResource": True},
    }
    resp = requests.post(
        "https://workspaceevents.googleapis.com/v1/subscriptions",
        headers={"Authorization": f"Bearer {creds.token}", "Content-Type": "application/json"},
        data=json.dumps(body),
        timeout=30,
    )
    print(resp.status_code)
    print(json.dumps(resp.json(), indent=2))
    resp.raise_for_status()


if __name__ == "__main__":
    main()
