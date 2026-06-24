# review-pr

A bot that watches one Google Chat space over **Cloud Pub/Sub**. Whenever a message contains a
GitHub Pull Request URL, it **approves** the PR and then **merges** it (merge commit, delete branch)
using the `gh` CLI, and posts a confirmation back into the message's thread via an incoming webhook.

To avoid GitHub's "you can't approve your own PR" rule, two accounts are configured and the bot
approves with whichever one is **not** the PR author.

## How it works

```
Google Chat space ──publishes MESSAGE event──▶ Pub/Sub topic ──pull──▶ subscriber (this app)
                                                                            │
                    1. only act on MESSAGE events from the configured space
                    2. extract the first GitHub PR URL from the text
                    3. look up the PR author; pick the non-author account
                    4. gh pr review <url> --approve --body "lgtm."
                    5. gh pr merge  <url> --merge --delete-branch
                    6. post "✅ Merged <url> (approved by <account>)" into the thread
```

Running over Pub/Sub means the app only makes outbound connections — no public endpoint, tunnel, or
JWT audience needed. It runs fine on localhost.

## Modules

| File | Responsibility |
|---|---|
| `config.py` | Settings loaded from env/`.env` (only place env is read) |
| `pr_url.py` | Extract the first GitHub PR URL from text |
| `chat.py` | Parse the Google Chat event payload |
| `github.py` | Look up author, pick non-author account, approve + merge via `gh` |
| `notify.py` | Post replies into the space via the incoming webhook |
| `handler.py` | The per-event pipeline tying the above together |
| `subscriber.py` | Pub/Sub pull subscriber + `review-pr-bot` entrypoint |

## Setup

Requires Poetry and the `gh` CLI on PATH, plus a Google Cloud project with a Pub/Sub topic +
subscription wired to a Chat app. See [`docs/google-chat-pubsub-setup.md`](docs/google-chat-pubsub-setup.md)
for the full Google Cloud walkthrough.

1. Install dependencies:
   ```bash
   poetry install
   ```
2. Copy `.env.template` to `.env` and fill in the values (space id, Pub/Sub subscription, webhook
   URL, service-account key path, and the two GitHub account/token pairs).
3. Run the subscriber:
   ```bash
   poetry run review-pr-bot
   ```

## Tests

```bash
poetry run pytest
poetry run ruff check src tests
```

## Operational notes

- **GitHub forbids approving your own PR** — each `GITHUB_ACCOUNT_n` must be the account's
  login/username, and at least one configured account must differ from the PR author.
- Branch protection / required checks must permit the merge for `gh pr merge` to succeed.
- Secrets (`.env`, the service-account `key.json`, webhook URL) are never committed.
