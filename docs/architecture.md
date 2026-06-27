# Architecture

A bot that watches **one** Google Chat space over Cloud Pub/Sub. When a message contains a GitHub
PR URL, it approves and merges the PR via the `gh` CLI, then replies in-thread and reacts to the
original message. Because Pub/Sub delivery is _pull-based_, the app only makes outbound connections
— there is no public endpoint to expose or secure.

## Event flow

```
┌──────────────────┐
│ Google Chat space│  human posts a message (maybe with a PR link)
└────────┬─────────┘
         │
         ▼
┌──────────────────────────┐
│ Workspace Events         │  space subscription (≈4h TTL, auto-renewed)
│ subscription             │
└────────┬─────────────────┘
         │ publishes
         ▼
┌───────────────────────────┐
│ chat-events Pub/Sub topic │
└────────┬──────────────────┘
         │ pull
         ▼
┌──────────────────────────┐
│ subscriber.py            │  pull loop; callback runs on MULTIPLE threads
│  _callback → always ack  │  decode JSON → handle_chat_event → ack (always)
└────────┬─────────────────┘
         │
         ▼
┌──────────────────────────┐
│ handler.py               │  per-event pipeline → exactly one Outcome
│  handle_chat_event       │  (see check-order.md for the decision sequence)
└────────┬─────────────────┘
         │ for an eligible PR link
         ▼
┌──────────────────────────┐
│ github.py                │  get_pr_status → approve_and_merge via `gh`
└──────────────────────────┘
         │
         ▼
   notify.py (thread reply)  +  reactions.py (add / remove emoji on the message)
```

The subscriber callback **always acks**, even on failure. Any exception is logged and swallowed so a
bad message is never re-delivered in a loop and never crashes the subscriber.

## Module map

| File               | Responsibility                                                           |
| ------------------ | ------------------------------------------------------------------------ |
| `config.py`        | `Settings` (pydantic-settings) — the **only** place env / `.env` is read |
| `subscriber.py`    | Pub/Sub pull loop + the `review-pr-bot` entrypoint                       |
| `handler.py`       | Per-event pipeline; `Outcome`, `PROTECTED_BASE_BRANCHES` live here       |
| `github.py`        | PR lookup, account selection, approve + merge via `gh`                   |
| `pr_url.py`        | Extract GitHub PR URL(s) from arbitrary message text                     |
| `chat.py`          | Parse the Google Chat / Workspace Events payload into a `ParsedEvent`    |
| `messages.py`      | Map raw `gh` / GraphQL errors to friendly, plain-English replies         |
| `notify.py`        | Post the thread reply via an incoming webhook (post-only)                |
| `reactions.py`     | Add / remove an emoji reaction via an authenticated Chat API call        |
| `dedup.py`         | Thread-safe, restart-persistent dedup guard (`state/dedup.json`)         |
| `logging_setup.py` | Coloured console (INFO) + datetime-stamped DEBUG file in `logs/`         |

## Key design decisions

### Pull-based Pub/Sub, no public endpoint

The app subscribes and pulls, so it only ever connects outbound. Nothing needs to accept inbound
HTTP, which removes a whole class of exposure and auth concerns.

### Two-account approve rule (`github.py`)

GitHub forbids approving your own PR. Two `(account, token)` pairs are configured, and
`_select_account` picks the first whose login ≠ the PR author. All `gh` calls go through `_run_gh`,
which injects only `GH_TOKEN` plus a minimal env passthrough (never the full parent environment) and
raises `GhError(step, message)` on any failure, where `step` is `"lookup" | "approve" | "merge"`.

### Every PR link gets exactly one answer

`handle_chat_event` guarantees that any message with a PR link resolves to exactly one `Outcome`
(an emoji + a reply). A PR link is never left silently unanswered — PR status, approve/merge result,
lookup failure, or any unexpected error all map to an `Outcome`.

### Immediate acknowledgement while a PR is processed

Approve + merge can take a few seconds, long enough to look like the bot missed the message. Once a
single PR link is confirmed, `handle_chat_event` posts an "On it…" reply and adds a 👀 reaction
(`EMOJI_WORKING`) right away. When processing finishes, the 👀 reaction is removed via
`remove_reaction` and replaced by the outcome emoji, leaving the message with exactly one final
reaction. `add_reaction` returns the created reaction's resource name so it can later be removed; the
removal is best-effort like every other side effect.

### Mandatory dedup before any side effect (`dedup.py`)

Pub/Sub is at-least-once and the callback is multi-threaded, so the same message can arrive twice
concurrently. `claim(message_name)` records each id under a lock — only the first delivery proceeds.
State is mirrored to `state/dedup.json` so a redelivery _after a restart_ is still rejected.

### Side-effect failures are logged, never raised

notify, reactions, and dedup persistence are best-effort. A failure in any of them is logged and
swallowed so it never crashes the subscriber or aborts the reply/reaction. Preserve this when
editing those paths.

### Friendly errors, raw text only in logs

`messages.friendly_gh_error` translates raw `gh` / GraphQL errors into plain-English replies via
ordered `(step, substring)` rules. The raw error text is logged but never shown to users.

### Protected base branches

`PROTECTED_BASE_BRANCHES` (`prezent`, `main`, `master`) are never auto-merged. The PR's base branch
is compared against this set case-insensitively; a match requires a human to merge manually.

## Conventions & gotchas

- **`config.py` is the only module that reads env.** Everything else imports `settings`. Tests set
  required env vars in `tests/conftest.py` before any import.
- Secrets live in `.env` and `.keys/` (both gitignored). **Never read `.env`** or commit secrets.
- `reactions.py` needs an authenticated Chat API call (OAuth token in `.keys/token.json`); webhooks
  cannot manage reactions. `notify.py` posts via an incoming webhook and is post-only. Removing a
  reaction needs the broad `chat.messages.reactions` scope — the create-only scope is not enough.
- The Workspace Events subscription expires (≈4h TTL). The bot renews it itself: `subscriber.py`
  runs a daemon thread that calls `manage_subscription.py ensure` on startup and every 3h. Full
  setup lives in `docs/google-chat-pubsub-setup.md` and `docs/workspace-events-auto-renewal.md`.
