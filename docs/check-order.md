# PR check order

This is the exact sequence of checks the bot runs when a Google Chat message arrives, from the
Pub/Sub callback down to the approve + merge. The order matters: each gate short-circuits, so a
message only reaches `approve_and_merge` after passing **every** check above it.

Two stages: the **event gates** (`handler.handle_chat_event`) decide whether the message is even
worth acting on, then the **PR eligibility checks** (`handler._process_pr`) decide whether the
specific PR may be merged.

## Stage 1 — event gates (`handle_chat_event`)

| # | Check | Source | If it fails |
|---|---|---|---|
| 1 | **Right space?** `event.space_name == settings.google_chat_space_id` | `handler.py:48` | Return silently — ignore events from any other space. |
| 2 | **Human sender?** `event.sender_type == "HUMAN"` | `handler.py:53` | Return silently. The bot's own webhook replies arrive as non-HUMAN; replying would infinite-loop. |
| 3 | **First delivery?** `claim(event.message_name)` | `handler.py:58` | Return silently. Pub/Sub is at-least-once + multi-threaded; a duplicate is skipped to avoid a double approve/merge. |
| 4 | **Any PR link?** `extract_pr_urls(event.text)` | `handler.py:64` | Reply "didn't spot a PR link" + react ❓ (`EMOJI_NO_LINK`). |
| 5 | **Exactly one PR link?** `len(urls) > 1` | `handler.py:74` | Reply "send just one at a time" + react ✋ (`EMOJI_MULTI`). Ambiguous, so no action. |

Only a message that passes all five — right space, human, first delivery, exactly one PR link —
reaches Stage 2. Before doing so, the bot **acknowledges immediately**: it posts an "On it…" reply
and adds a 👀 reaction (`EMOJI_WORKING`) so a slow approve/merge never looks like a missed message.
The single URL (`urls[0]`) is then handed to `_process_pr`. Once an outcome is reached, the 👀
reaction is removed and replaced by the outcome emoji below.

## Stage 2 — PR eligibility checks (`_process_pr`)

First, `get_pr_status(url)` is called (`gh pr view ... --json`). A lookup failure raises
`GhError(step="lookup")`, caught by the caller and reported via `friendly_gh_error`. On success the
PR is run through these gates **in order** — the first match wins and returns immediately:

| # | Check | Outcome if matched | Emoji |
|---|---|---|---|
| 1 | `state == "MERGED"` | "Already merged — nothing to do." | 🚫 `EMOJI_NOOP` |
| 2 | `state == "CLOSED"` | "This PR is closed, so I'll leave it alone." | ⚠️ `EMOJI_ATTENTION` |
| 3 | `is_draft` | "Still a draft — I'll merge once marked ready." | ⚠️ `EMOJI_ATTENTION` |
| 4 | `base_branch.lower() in PROTECTED_BASE_BRANCHES` | "Targets a protected branch — merge manually." | ⚠️ `EMOJI_ATTENTION` |
| 5 | `mergeable == "CONFLICTING"` or `merge_state == "DIRTY"` | "Has merge conflicts — resolve and resend." | ⚠️ `EMOJI_ATTENTION` |

`PROTECTED_BASE_BRANCHES` = `{prezent, main, master}`, compared case-insensitively.

If **none** of the five gates match, the PR is eligible and the bot proceeds to approve + merge.

## Stage 3 — approve + merge (`approve_and_merge`)

1. **`_select_account(author)`** — pick the first configured `(account, token)` whose login ≠ the PR
   author. GitHub forbids approving your own PR; if no account qualifies, raise
   `GhError(step="approve")`.
2. **`gh pr review --approve`** — approve with the selected non-author account. Failure raises
   `GhError(step="approve")`.
3. **`gh pr merge --merge --delete-branch`** — merge and delete the branch. Failure raises
   `GhError(step="merge")`.

On success: reply "✅ Approved & merged! Approved by `<account>`, branch deleted." + react ✅
(`EMOJI_DONE`).

## Error handling around Stage 2 / 3

`_process_pr` runs inside a try/except in `handle_chat_event`:

- **`GhError`** (any of lookup/approve/merge) → `_gh_error_outcome`: logs the raw text, replies with
  `friendly_gh_error(step, message)`, reacts ⚠️.
- **Any other exception** → logged, generic "something went wrong" reply, reacts ⚠️.

Either way, the message **always** gets a reply + reaction — a PR link is never left unanswered.

## End-to-end summary

```
message
  │
  ├─ not configured space?         → ignore
  ├─ not HUMAN sender?             → ignore (loop guard)
  ├─ duplicate delivery?           → ignore (dedup)
  ├─ no PR link?                   → reply + ❓
  ├─ more than one PR link?        → reply + ✋
  │
  ▼ exactly one PR link
ack: "On it…" reply + 👀          (removed and replaced by the outcome emoji below)
  │
get_pr_status (gh pr view)         → lookup error → friendly reply + ⚠️
  │
  ├─ MERGED?                       → reply + 🚫
  ├─ CLOSED?                       → reply + ⚠️
  ├─ draft?                        → reply + ⚠️
  ├─ protected base branch?        → reply + ⚠️
  ├─ conflicting / dirty?          → reply + ⚠️
  │
  ▼ eligible
approve_and_merge                  → approve/merge error → friendly reply + ⚠️
  │
  ▼ success
reply "Approved & merged!" + ✅
```
