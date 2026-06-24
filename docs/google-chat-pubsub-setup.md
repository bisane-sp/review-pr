# Google Chat → Pub/Sub setup

This bot receives Chat messages over **Cloud Pub/Sub** (not a public HTTP endpoint), so it runs
anywhere with outbound internet — including localhost. No public URL, no tunnel, no JWT audience.

```
Google Chat space ──publishes MESSAGE event──▶ Pub/Sub topic ──pull──▶ subscriber (this app)
                                                                            │
                              approve (non-author account) + merge via gh   │
                              post "✅ Merged" back via the incoming webhook ◀┘
```

## One-time Google Cloud setup

You can do all of this with the `gcloud` CLI (Option A) or entirely in the Cloud Console UI
(Option B) if you don't have `gcloud` installed.

### Option A — gcloud CLI

1. **Enable APIs** in your Cloud project: **Google Chat API** and **Cloud Pub/Sub API**.
2. **Create a Pub/Sub topic**, e.g. `chat-events`:
   ```bash
   gcloud pubsub topics create chat-events
   ```
3. **Let Google Chat publish to it.** Grant the Chat service account the Publisher role on the topic:
   ```bash
   gcloud pubsub topics add-iam-policy-binding chat-events \
     --member='serviceAccount:chat-api-push@system.gserviceaccount.com' \
     --role='roles/pubsub.publisher'
   ```
4. **Create a pull subscription** the app will read from:
   ```bash
   gcloud pubsub subscriptions create chat-events-sub --topic=chat-events
   ```
5. **Create a service account** for the app and give it Subscriber access, then download a key:
   ```bash
   gcloud iam service-accounts create review-pr-bot
   gcloud pubsub subscriptions add-iam-policy-binding chat-events-sub \
     --member='serviceAccount:review-pr-bot@YOUR_PROJECT.iam.gserviceaccount.com' \
     --role='roles/pubsub.subscriber'
   gcloud iam service-accounts keys create key.json \
     --iam-account=review-pr-bot@YOUR_PROJECT.iam.gserviceaccount.com
   ```
6. **Configure the Chat app** (Google Chat API → Configuration → Connection settings):
   - Select **Cloud Pub/Sub**.
   - Enter the topic name: `projects/YOUR_PROJECT/topics/chat-events`.
7. **Add the Chat app to your space** so it receives the space's messages.

### Option B — Cloud Console (no gcloud)

1. **Enable APIs:** Console → APIs & Services → Library → enable **Google Chat API** and
   **Cloud Pub/Sub API**.
2. **Create the topic:** search **Pub/Sub** → **Topics** → **Create topic** → ID `chat-events`
   (leave "Add a default subscription" checked) → **Create**.
3. **Subscription:** if step 2's default subscription wasn't created, go to **Subscriptions** →
   **Create subscription** → ID `chat-events-sub`, Topic `chat-events`, Delivery type **Pull**.
4. **Let Chat publish:** open the **topic** → **Permissions** → **Add principal** →
   principal `chat-api-push@system.gserviceaccount.com`, role **Pub/Sub Publisher** → **Save**.
5. **Service account + key:** IAM & Admin → **Service Accounts** → **Create service account**
   (`review-pr-bot`). Then on the **subscription** → Permissions, add that service account with role
   **Pub/Sub Subscriber**. Finally, on the service account → **Keys** → **Add key → JSON** to download
   `key.json`.
6. **Configure the Chat app:** Google Chat API → Configuration → Connection settings → **Cloud
   Pub/Sub** → topic `projects/YOUR_PROJECT/topics/chat-events`.
7. **Add the Chat app to your space.**

## App configuration (`.env`)

```bash
GOOGLE_CHAT_SPACE_ID=spaces/AAQA1ukurw4
PUBSUB_SUBSCRIPTION=projects/YOUR_PROJECT/subscriptions/chat-events-sub
GOOGLE_CHAT_WEBHOOK_URL=https://chat.googleapis.com/v1/spaces/.../messages?key=...&token=...
GOOGLE_APPLICATION_CREDENTIALS=/absolute/path/to/key.json
GITHUB_ACCOUNT_1=...
GITHUB_TOKEN_1=...
GITHUB_ACCOUNT_2=...
GITHUB_TOKEN_2=...
```

## Run

```bash
poetry install
poetry run review-pr-bot
```

The process subscribes and blocks, processing each message as it arrives. Post a PR link in the
space to trigger an approve + merge; the confirmation is posted back into the same thread via the
incoming webhook.
