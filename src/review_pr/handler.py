"""Process a single Google Chat event: detect a PR link, approve + merge, reply + react.

Replies into the message's thread for *every* human message in the configured space, and adds an
emoji reaction to the original message summarising the outcome:
  ✅ approved + merged   🚫 already merged (no action needed)   ⚠️ needs the user's action
For a PR link, *every* outcome is reported — PR status, the approve/merge result, a lookup
failure, or any unexpected error. No PR link ever goes unanswered.
"""

import logging
from dataclasses import dataclass

from .chat import parse_message_event
from .config import settings
from .github import GhError, approve_and_merge, get_pr_status
from .messages import friendly_gh_error
from .notify import post_message
from .pr_url import extract_pr_url
from .reactions import add_reaction

logger = logging.getLogger(__name__)

# Reaction emojis by outcome category.
EMOJI_DONE = "✅"  # the app approved + merged
EMOJI_NOOP = "🚫"  # already merged — nothing for anyone to do
EMOJI_ATTENTION = "⚠️"  # the user needs to act (closed/draft/blocked/failed/error)


@dataclass
class Outcome:
    """A reaction emoji plus the thread reply text for one processed PR link."""

    emoji: str
    text: str


def handle_chat_event(payload: dict) -> None:
    """Handle one Chat event. Acts only on human messages from the configured space."""
    event = parse_message_event(payload)

    if event.space_name != settings.google_chat_space_id:
        return

    # Loop guard: only respond to humans. The bot's own webhook replies arrive as non-HUMAN
    # senders; replying to those would trigger an infinite loop.
    if event.sender_type != "HUMAN":
        return

    logger.info("Message in %s: %s", event.space_name, event.text)

    url = extract_pr_url(event.text)
    if not url:
        post_message(
            "🔍 I didn't spot a GitHub PR link in that message. Drop one in and I'll approve & "
            "merge it for you.",
            event.thread_name,
        )
        return

    # Every branch below resolves to exactly one outcome, so a PR link is never left unanswered.
    try:
        outcome = _process_pr(url)
    except GhError as exc:
        outcome = _gh_error_outcome(url, exc)
    except Exception:
        logger.exception("Unexpected error handling %s", url)
        outcome = Outcome(
            EMOJI_ATTENTION,
            "❌ Something went wrong while handling this PR. I've logged the details for the team to "
            "look into.",
        )

    post_message(outcome.text, event.thread_name)
    if event.message_name:
        add_reaction(event.message_name, outcome.emoji)


def _process_pr(url: str) -> Outcome:
    """Look up the PR, then approve + merge it when eligible. Returns the outcome.

    Raises ``GhError`` for any ``gh`` failure (handled by the caller's catch-all).
    """
    status = get_pr_status(url)
    if status.state == "MERGED":
        return Outcome(EMOJI_NOOP, "ℹ️ This PR is already merged — nothing for me to do.")
    if status.state == "CLOSED":
        return Outcome(EMOJI_ATTENTION, "🚫 This PR is closed, so I'll leave it alone.")
    if status.is_draft:
        return Outcome(
            EMOJI_ATTENTION,
            "📝 This PR is still a draft. I'll approve & merge it once it's marked ready for review.",
        )

    account = approve_and_merge(url, status.author)
    return Outcome(EMOJI_DONE, f"✅ *Approved & merged!* Approved by {account}, branch deleted. 🎉")


def _gh_error_outcome(url: str, exc: GhError) -> Outcome:
    """Map a ``GhError`` to the outcome for its failing step (always needs the user's attention).

    The raw ``gh`` text is logged, not shown — the reply gets a plain-English translation.
    """
    logger.warning("gh %s failed for %s: %s", exc.step, url, exc.message)
    return Outcome(EMOJI_ATTENTION, friendly_gh_error(exc.step, exc.message))
