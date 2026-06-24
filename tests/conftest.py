"""Set required env vars before any review_pr module imports its Settings."""

import os

os.environ.setdefault("GOOGLE_CHAT_SPACE_ID", "spaces/TEST")
os.environ.setdefault("GOOGLE_CHAT_WEBHOOK_URL", "https://chat.example/webhook?key=k&token=t")
os.environ.setdefault("PUBSUB_SUBSCRIPTION", "projects/test/subscriptions/test-sub")
os.environ.setdefault("GITHUB_ACCOUNT_1", "bot-one")
os.environ.setdefault("GITHUB_TOKEN_1", "token-1")
os.environ.setdefault("GITHUB_ACCOUNT_2", "bot-two")
os.environ.setdefault("GITHUB_TOKEN_2", "token-2")
os.environ.setdefault("GH_TIMEOUT_SECONDS", "5")
