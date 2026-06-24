from unittest.mock import patch

from review_pr import handler
from review_pr.handler import EMOJI_ATTENTION, EMOJI_DONE, EMOJI_NOOP
from review_pr.github import GhError, PrStatus

SPACE = "spaces/TEST"
URL = "https://github.com/org/repo/pull/1"
THREAD = "spaces/TEST/threads/T1"
MESSAGE = "spaces/TEST/messages/M1"


def _event(text, space=SPACE, thread=THREAD, sender_type="HUMAN", message_name=MESSAGE):
    """A Workspace Events message payload (no top-level "type")."""
    return {
        "space": {"name": space},
        "message": {
            "name": message_name,
            "text": text,
            "thread": {"name": thread},
            "sender": {"type": sender_type},
        },
    }


def _status(state="OPEN", is_draft=False, author="pr-author"):
    return PrStatus(state=state, is_draft=is_draft, author=author, mergeable="MERGEABLE", merge_state="CLEAN")


def test_open_pr_approves_merges_replies_and_reacts():
    with (
        patch.object(handler, "get_pr_status", return_value=_status()),
        patch.object(handler, "approve_and_merge", return_value="bot-one") as merge,
        patch.object(handler, "post_message") as post,
        patch.object(handler, "add_reaction") as react,
    ):
        handler.handle_chat_event(_event(URL))

    merge.assert_called_once_with(URL, "pr-author")
    post.assert_called_once_with(f"✅ Approved & merged {URL} (by bot-one)", THREAD)
    react.assert_called_once_with(MESSAGE, EMOJI_DONE)


def test_wrong_space_does_nothing():
    with (
        patch.object(handler, "get_pr_status") as status,
        patch.object(handler, "post_message") as post,
        patch.object(handler, "add_reaction") as react,
    ):
        handler.handle_chat_event(_event(URL, space="spaces/OTHER"))

    status.assert_not_called()
    post.assert_not_called()
    react.assert_not_called()


def test_non_human_sender_is_ignored():
    # Loop guard: the bot's own webhook replies must never trigger a reply.
    with (
        patch.object(handler, "get_pr_status") as status,
        patch.object(handler, "approve_and_merge") as merge,
        patch.object(handler, "post_message") as post,
        patch.object(handler, "add_reaction") as react,
    ):
        handler.handle_chat_event(_event(f"✅ Approved & merged {URL}", sender_type="BOT"))

    status.assert_not_called()
    merge.assert_not_called()
    post.assert_not_called()
    react.assert_not_called()


def test_message_without_pr_url_replies_no_link_and_does_not_react():
    with (
        patch.object(handler, "get_pr_status") as status,
        patch.object(handler, "post_message") as post,
        patch.object(handler, "add_reaction") as react,
    ):
        handler.handle_chat_event(_event("good morning team"))

    status.assert_not_called()
    post.assert_called_once_with("🔍 No GitHub PR link found in this message.", THREAD)
    react.assert_not_called()


def test_already_merged_reacts_noop_and_skips():
    with (
        patch.object(handler, "get_pr_status", return_value=_status(state="MERGED")),
        patch.object(handler, "approve_and_merge") as merge,
        patch.object(handler, "post_message") as post,
        patch.object(handler, "add_reaction") as react,
    ):
        handler.handle_chat_event(_event(URL))

    merge.assert_not_called()
    assert "Already merged" in post.call_args[0][0]
    react.assert_called_once_with(MESSAGE, EMOJI_NOOP)


def test_closed_pr_reacts_attention_and_skips():
    with (
        patch.object(handler, "get_pr_status", return_value=_status(state="CLOSED")),
        patch.object(handler, "approve_and_merge") as merge,
        patch.object(handler, "post_message") as post,
        patch.object(handler, "add_reaction") as react,
    ):
        handler.handle_chat_event(_event(URL))

    merge.assert_not_called()
    assert "closed" in post.call_args[0][0]
    react.assert_called_once_with(MESSAGE, EMOJI_ATTENTION)


def test_draft_pr_reacts_attention_and_skips():
    with (
        patch.object(handler, "get_pr_status", return_value=_status(is_draft=True)),
        patch.object(handler, "approve_and_merge") as merge,
        patch.object(handler, "post_message") as post,
        patch.object(handler, "add_reaction") as react,
    ):
        handler.handle_chat_event(_event(URL))

    merge.assert_not_called()
    assert "draft" in post.call_args[0][0]
    react.assert_called_once_with(MESSAGE, EMOJI_ATTENTION)


def test_lookup_failure_reacts_attention_and_replies():
    with (
        patch.object(handler, "get_pr_status", side_effect=GhError("lookup", "not found")),
        patch.object(handler, "approve_and_merge") as merge,
        patch.object(handler, "post_message") as post,
        patch.object(handler, "add_reaction") as react,
    ):
        handler.handle_chat_event(_event(URL))

    merge.assert_not_called()
    assert "Couldn't read PR" in post.call_args[0][0]
    react.assert_called_once_with(MESSAGE, EMOJI_ATTENTION)


def test_approve_failure_reacts_attention_and_replies():
    with (
        patch.object(handler, "get_pr_status", return_value=_status()),
        patch.object(handler, "approve_and_merge", side_effect=GhError("approve", "no perms")),
        patch.object(handler, "post_message") as post,
        patch.object(handler, "add_reaction") as react,
    ):
        handler.handle_chat_event(_event(URL))

    text, thread = post.call_args[0]
    assert "Failed to approve" in text
    assert thread == THREAD
    react.assert_called_once_with(MESSAGE, EMOJI_ATTENTION)


def test_merge_failure_reacts_attention_and_replies():
    with (
        patch.object(handler, "get_pr_status", return_value=_status()),
        patch.object(handler, "approve_and_merge", side_effect=GhError("merge", "blocked")),
        patch.object(handler, "post_message") as post,
        patch.object(handler, "add_reaction") as react,
    ):
        handler.handle_chat_event(_event(URL))

    assert "Approved but merge failed" in post.call_args[0][0]
    react.assert_called_once_with(MESSAGE, EMOJI_ATTENTION)


def test_unexpected_error_still_replies_and_reacts():
    # A non-GhError exception (e.g. a bug) must still produce a thread reply, never a silent drop.
    with (
        patch.object(handler, "get_pr_status", side_effect=ValueError("boom")),
        patch.object(handler, "post_message") as post,
        patch.object(handler, "add_reaction") as react,
    ):
        handler.handle_chat_event(_event(URL))

    text, thread = post.call_args[0]
    assert "Unexpected error" in text
    assert thread == THREAD
    react.assert_called_once_with(MESSAGE, EMOJI_ATTENTION)
