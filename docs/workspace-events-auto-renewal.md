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
| `scripts/renew_cron.sh` | wrapper a scheduler calls; runs `ensure` | tracked |
| `.keys/oauth_client.json` | OAuth client (Desktop) used for user sign-in | **ignored** |
| `.keys/token.json` | saved user creds incl. refresh token (headless renew) | **ignored** |
| `.keys/subscription_AAQAXYyFGos.txt` | the active subscription's resource name | **ignored** |
| `.keys/review-pr-500320-*.json` | GCP service account key (Pub/Sub) | **ignored** |

`.keys/` is git-ignored so none of these secrets are ever committed. Everything the renewal
needs lives outside `temp/` (which is throwaway/ignored) so it survives.

## Renew manually

```bash
poetry run python scripts/manage_subscription.py ensure spaces/AAQAXYyFGos
```

Run this any time within 4h of the last renewal. That's all renewal *is* — the rest is just
automating this command on a timer.

## Automate it (launchd, every 3 hours)

Renew every 3h to stay comfortably under the 4h TTL. A launchd **LaunchAgent** runs the wrapper
on a timer (and at login). This installs a persistent background job, so review before enabling.

1. Create `~/Library/LaunchAgents/com.review-pr.events-renew.plist`:

   ```xml
   <?xml version="1.0" encoding="UTF-8"?>
   <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
   <plist version="1.0">
   <dict>
       <key>Label</key>
       <string>com.review-pr.events-renew</string>
       <key>ProgramArguments</key>
       <array>
           <string>/bin/zsh</string>
           <string>/Users/bisane.s/office_work/projects/review-pr/scripts/renew_cron.sh</string>
       </array>
       <key>StartInterval</key>
       <integer>10800</integer>
       <key>RunAtLoad</key>
       <true/>
       <key>StandardOutPath</key>
       <string>/Users/bisane.s/office_work/projects/review-pr/temp/renew.launchd.out.log</string>
       <key>StandardErrorPath</key>
       <string>/Users/bisane.s/office_work/projects/review-pr/temp/renew.launchd.err.log</string>
   </dict>
   </plist>
   ```

2. Load it:

   ```bash
   launchctl load ~/Library/LaunchAgents/com.review-pr.events-renew.plist
   ```

3. Check / unload:

   ```bash
   launchctl list | grep review-pr            # confirm it's registered
   tail -f temp/renew.log                      # watch renewals
   launchctl unload ~/Library/LaunchAgents/com.review-pr.events-renew.plist   # stop
   ```

Caveats: launchd only fires while the Mac is awake; a missed window (laptop asleep > 4h) lets the
subscription lapse — `ensure` handles that by recreating it on the next run. The subscriber
(`review-pr-bot`) is a separate process; it must also be running to actually log the events.

## Troubleshooting

- **Renew returns 401/invalid_grant:** the refresh token was revoked. Delete `.keys/token.json`
  and run `ensure` once interactively to re-authorize.
- **No events despite ACTIVE subscription:** confirm `chat-api-push@system.gserviceaccount.com`
  still has **Pub/Sub Publisher** on the topic, and that the subscriber is running.
- **Wrong space:** the subscription targets `spaces/AAQAXYyFGos`. To switch, run
  `ensure spaces/<NEW_ID>` and update `GOOGLE_CHAT_SPACE_ID` in `.env`.
