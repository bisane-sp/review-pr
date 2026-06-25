# Capturing all space messages + auto-renewal

This explains how *every* message in a Google Chat space reaches the bot, why the mechanism
**expires**, and how to keep it alive automatically.

## Why a subscription is needed at all

A normal Google Chat app added to a space only receives an event when it is **@mentioned**,
when a **slash command** is used, or inside a **direct message**. It never sees plain messages
other people post. To capture *all* messages, we use the **Google Workspace Events API**: a
subscription attached to the space that emits `google.workspace.chat.message.v1.created` for
every new message and delivers it to our Pub/Sub topic `chat-events`. The existing subscriber
(`poetry run review-pr-bot`) then reads them like any other Pub/Sub message.

```
Chat space ─every message→ Workspace Events subscription ─publish→ Pub/Sub topic
                                                                       │ pull
                                                            review-pr-bot (logs it)
```

## Why it expires (the core of "renewal")

Chat message subscriptions are **short-lived**. Because our payload includes the full message
resource (`payloadOptions.includeResource = true`), the **maximum TTL is ~4 hours**. When the
subscription's `expireTime` passes, Google stops publishing events and the subscription moves to
a suspended state (recoverable for a short window, then deleted). The terminal simply goes quiet.

So "keeping it working" = **renewing before `expireTime`**.

## How renewal works

Renewal is a single API call — `PATCH .../subscriptions/{name}?updateMask=ttl` with body
`{"ttl": "0s"}`. The special value `0s` means *"extend to the maximum allowed"* (i.e. another
~4 hours from now). No need to delete and recreate.

Two important constraints:

1. **User auth only.** Creating/updating a Chat subscription must be done as a **real user who is
   a member of the space** — not the service account. (App auth can only list/get/delete.)
2. **No browser needed after the first time.** The first sign-in requested offline access, so a
   **refresh token** was saved to `.keys/token.json`. Every later renewal silently exchanges that
   refresh token for a fresh access token — fully headless.

`scripts/manage_subscription.py ensure spaces/<ID>` does exactly this: it renews the stored
subscription, and if it has already expired beyond recovery, it transparently creates a new one
and saves the new name.

## File layout (what lives where, and why)

| File | Purpose | Git |
|---|---|---|
| `scripts/manage_subscription.py` | create / renew / delete / ensure subscriptions | tracked |
| `.keys/oauth_client.json` | OAuth client (Desktop) used for user sign-in | **ignored** |
| `.keys/token.json` | saved user creds incl. refresh token (headless renew) | **ignored** |
| `.keys/subscription_AAQA1ukurw4.txt` | the active subscription's resource name | **ignored** |
| `.keys/review-pr-500320-*.json` | GCP service account key (Pub/Sub) | **ignored** |

`.keys/` is git-ignored so none of these secrets are ever committed. Everything the renewal
needs lives outside `temp/` (which is throwaway/ignored) so it survives.

## Renew manually

```bash
poetry run python scripts/manage_subscription.py ensure spaces/AAQA1ukurw4
```

Run this any time within 4h of the last renewal. That's all renewal *is* — the rest is just
automating this command on a timer.

## Automatic renewal (built into the bot)

The subscriber renews itself — there is no separate scheduler, cron job, or LaunchAgent. On
startup `review-pr-bot` spawns a daemon thread (`subscriber._renewal_loop`) that runs
`manage_subscription.py ensure` immediately and then every **3 hours**, staying comfortably under
the ~4h TTL. Because renewal lives inside the bot process:

- Starting the bot (`make run`, `make bot`, or `poetry run review-pr-bot`) immediately ensures a
  live subscription, then keeps it alive for as long as the process runs.
- A failed renewal is logged and retried on the next cycle — it never crashes the subscriber.
- If the subscription has already lapsed beyond recovery, `ensure` transparently recreates it.

Renewal only happens while the bot is running. If the process is down for >4h the subscription
lapses, but the next start renews/recreates it.

## Troubleshooting

- **Renew returns 401/invalid_grant:** the refresh token was revoked. Delete `.keys/token.json`
  and run `ensure` once interactively to re-authorize.
- **No events despite ACTIVE subscription:** confirm `chat-api-push@system.gserviceaccount.com`
  still has **Pub/Sub Publisher** on the topic, and that the subscriber is running.
- **Wrong space:** the subscription targets `spaces/AAQA1ukurw4`. To switch, run
  `ensure spaces/<NEW_ID>` and update `GOOGLE_CHAT_SPACE_ID` in `.env`.
