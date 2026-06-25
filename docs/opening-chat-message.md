# ⚙️ Welcome to the Review-PRs space!

## What the bot does

Drop a PR link here and it **approves and merges** the PR. Once done, it replies in-thread and reacts to your message with an emoji so you know the outcome at a glance. Every PR link gets exactly one answer — it's never left hanging.

## How to use it

1. Paste a GitHub PR URL into this space (a plain message, not inside a thread). One PR link per message — the bot handles a single PR per message.
2. Wait a moment — the bot picks it up automatically.
3. Read its in-thread reply + the emoji reaction:
   - ✅ approved & merged
   - ❓ no PR link found in the message
   - ⚠️ / other → something blocked it (draft PR, merge conflicts, or a protected base branch like `main`/`master`/`prezent`, which are never auto-merged)

No commands, no buttons — just paste the link.

## Core idea

Approving and merging a PR is usually a few clicks of context-switching out of chat. Since we share PR links anyway, this space turns "someone please merge this" into a zero-click action — the link *is* the request.

## How it works (under the hood)

- The bot watches this space over **Google Cloud Pub/Sub** (pull-based), so it only makes outbound connections — no public endpoint, nothing exposed.
- A Chat message → Workspace Events → Pub/Sub → the bot's subscriber, which extracts any PR URL and resolves its status.
- It runs all GitHub actions through the `gh` CLI. It supports GitHub's "you can't approve your own PR" rule by picking an account whose login isn't the PR author — though **right now only one GitHub account is configured**, so PRs authored by that account can't be auto-approved yet (a second account can be added later to cover that case).
- Before merging it checks state, draft status, merge conflicts, and protected base branches — and raw errors are translated into plain-English replies (so you get "this PR has conflicts", not a wall of CLI output).
- It's safe against duplicates and restarts (built-in dedup), and any link always resolves to a single clear outcome.

## Future scope

An automated **review step** can be added on top of this flow — actually reviewing the code before it approves and merges (that's why it lives in the "Review-PRs" space). For now it's approve-and-merge only.

Paste a PR link to get started. 🚀
