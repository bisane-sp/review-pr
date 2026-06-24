# Project setup — end to end

How `review-pr` was set up from nothing: the local Python project, the Google Cloud wirings that let
a Chat message reach the bot, the GitHub side that lets it approve + merge, and the background jobs
that keep it alive. This is the "big picture" walkthrough — the per-area deep dives live in
[`google-chat-pubsub-setup.md`](google-chat-pubsub-setup.md) and
[`workspace-events-auto-renewal.md`](workspace-events-auto-renewal.md), and the runtime design is in
[`architecture.md`](architecture.md).

GCP project used throughout: **`review-pr-500320`**. Chat space: **`spaces/AAQA1ukurw4`**.

## The shape of it

```
┌────────────────┐   message    ┌───────────────────────┐  publish   ┌─────────────────┐
│ Google Chat    │─────────────▶│ Workspace Events      │───────────▶│ Pub/Sub topic   │
│ space (humans) │  (any post)  │ subscription (~4h TTL)│            │ chat-events     │
└────────────────┘              └───────────────────────┘            └────────┬────────┘
        ▲                                                                     │ pull
        │ webhook reply + emoji reaction                                      ▼
        │                                                           ┌──────────────────┐
        └────────────────────────────────────────────────────────── │ review-pr-bot    │
                                                                    │ (this app)       │
                                                                    └────────┬─────────┘
                                                                             │ gh CLI
                                                                             ▼
                                                                    ┌──────────────────┐
                                                                    │ GitHub: approve  │
                                                                    │ + merge the PR   │
                                                                    └──────────────────┘
```

Everything the bot does is **outbound** — it pulls from Pub/Sub and calls GitHub/Chat APIs. There is
no public endpoint, so it runs fine on a laptop or any box with internet access.

## 1. Local project

- **Python ≥ 3.12, managed with Poetry.** Source lives under `src/review_pr/` (packaged via the
  `packages` entry in `pyproject.toml`); the console script `review-pr-bot` maps to
  `review_pr.subscriber:run`.
- **Install + run:**
  ```bash
  poetry install
  poetry run review-pr-bot
  ```
- **Config is env-only.** `src/review_pr/config.py` (`Settings`, pydantic-settings) is the *only*
  place env / `.env` is read; every other module imports the `settings` singleton. Copy
  `.env.template` → `.env` and fill it in (see [§5](#5-configuration-env)).
- **Secrets never get committed.** `.gitignore` excludes `.env`, `.keys/`, `state/`, and `logs/`.

## 2. Google Cloud wirings

Done once, in GCP project `review-pr-500320`. Full CLI + Console steps are in
[`google-chat-pubsub-setup.md`](google-chat-pubsub-setup.md); the essentials:

1. **Enable APIs:** Google Chat API, Cloud Pub/Sub API, and the Google Workspace Events API.
2. **Pub/Sub topic** `chat-events` — `projects/review-pr-500320/topics/chat-events`.
3. **Let Chat publish to it:** grant `chat-api-push@system.gserviceaccount.com` the
   **Pub/Sub Publisher** role on the topic. Without this, Chat silently publishes nothing.
4. **Pull subscription** `chat-events-sub` on that topic — this is what the app reads.
5. **Service account** `review-pr-bot@review-pr-500320.iam.gserviceaccount.com` with **Pub/Sub
   Subscriber** on the subscription; its JSON key is downloaded into `.keys/` and pointed at by
   `GOOGLE_APPLICATION_CREDENTIALS`. This is the identity the *running bot* authenticates as to pull.
6. **Chat app connection settings:** Google Chat API → Configuration → Connection settings →
   **Cloud Pub/Sub**, topic `projects/review-pr-500320/topics/chat-events`.
7. **Add the Chat app to the space** so it has access to the space's messages.

### Why a Workspace Events subscription (not just the Chat app)

A plain Chat app only receives an event when it's **@mentioned**, hit with a **slash command**, or
DM'd — it never sees ordinary messages people post. To act on *any* PR link dropped in the space, a
**Workspace Events subscription** is attached to the space; it emits
`google.workspace.chat.message.v1.created` for every new message and delivers it to the `chat-events`
topic. `scripts/manage_subscription.py create` sets this up. Details:
[`workspace-events-auto-renewal.md`](workspace-events-auto-renewal.md).

### Two identities, on purpose

| Identity | Stored as | Used for | Why it can't be the other |
|---|---|---|---|
| **Service account** | `.keys/*.json` (`GOOGLE_APPLICATION_CREDENTIALS`) | pulling Pub/Sub messages | App auth can't create/renew a Chat subscription |
| **Real user (OAuth)** | `.keys/oauth_client.json` + `.keys/token.json` | create/renew the subscription; add emoji reactions | Must be a human member of the space |

The OAuth client is a **Desktop** client; first run opens a browser for consent, then a **refresh
token** is saved to `.keys/token.json` so every later renewal/reaction call runs headless. The
scopes requested are `chat.messages.readonly` (manage the subscription) and
`chat.messages.reactions.create` (let `reactions.py` react).

### The incoming webhook

Replies ("✅ Merged …" / failure messages) are posted back into the thread via a Google Chat
**incoming webhook** (`GOOGLE_CHAT_WEBHOOK_URL`). Webhooks are post-only — that's why reactions need
the OAuth path above instead.

## 3. GitHub side

The bot approves and merges through the **`gh` CLI** (must be on `PATH`). GitHub forbids approving
your own PR, so **two** GitHub accounts are configured as `(account, token)` pairs. At runtime
`github.py::_select_account` picks the first pair whose login ≠ the PR author, then approves with
that account and merges. Each token is a Personal Access Token with repo + PR permissions.

## 4. Keeping it running

Two independent processes — both must be up for the bot to work:

1. **The subscriber** (`review-pr-bot`) — pulls and processes messages. `scripts/start_bot.sh`
   launches it in a detached tmux session named `prbot`.
2. **The renewer** — the Workspace Events subscription has a **~4h TTL** (because the payload
   includes the full message resource). `scripts/renew_cron.sh` runs
   `manage_subscription.py ensure` (renew; recreate if lapsed), installed as a **launchd
   LaunchAgent** firing every 3h and at login. Full instructions + the plist:
   [`workspace-events-auto-renewal.md`](workspace-events-auto-renewal.md).

Renew manually any time within the TTL window:
```bash
poetry run python scripts/manage_subscription.py ensure spaces/AAQA1ukurw4
```

## 5. Configuration (`.env`)

Copy `.env.template` and fill in:

| Variable | What it is |
|---|---|
| `GOOGLE_CHAT_SPACE_ID` | The one space the bot acts in, e.g. `spaces/AAQA1ukurw4` |
| `PUBSUB_SUBSCRIPTION` | `projects/review-pr-500320/subscriptions/chat-events-sub` |
| `GOOGLE_APPLICATION_CREDENTIALS` | Absolute path to the service-account key JSON in `.keys/` |
| `GOOGLE_CHAT_WEBHOOK_URL` | Incoming-webhook URL for posting replies |
| `GITHUB_ACCOUNT_1` / `GITHUB_TOKEN_1` | First approver account + PAT |
| `GITHUB_ACCOUNT_2` / `GITHUB_TOKEN_2` | Second approver account + PAT (the non-author one is used) |
| `GH_TIMEOUT_SECONDS` | Per-`gh`-call timeout (default 60) |
| `LOG_LEVEL` | Console verbosity; the DEBUG log file is always written under `logs/` |
| `CHAT_EVENTS_TOPIC` / `OAUTH_CLIENT_SECRETS` | Only used by the one-off subscription setup script |

## 6. First-run order

1. `poetry install`
2. Do the Google Cloud wirings ([§2](#2-google-cloud-wirings)) and download the service-account key.
3. Fill in `.env`.
4. Create the Workspace Events subscription (opens a browser once for OAuth consent):
   `poetry run python scripts/manage_subscription.py create spaces/AAQA1ukurw4`
5. Start the bot: `poetry run review-pr-bot` (or `scripts/start_bot.sh`).
6. Install the renewal LaunchAgent so the subscription never lapses.
7. Drop a PR link in the space — the bot approves, merges, replies in-thread, and reacts.
</content>
</invoke>
