from unittest.mock import patch

import pytest

from review_pr import dedup, handler
from review_pr.handler import EMOJI_ATTENTION, EMOJI_DONE, EMOJI_NOOP
from review_pr.github import GhError, PrStatus

SPACE = "spaces/TEST"
URL = "https://github.com/org/repo/pull/1"
THREAD = "spaces/TEST/threads/T1"
MESSAGE = "spaces/TEST/messages/M1"


@pytest.fixture(autouse=True)
def _clear_dedup():
    """Reset the dedup history so each test's message id is seen as fresh."""
    dedup._seen.clear()
    yield
    dedup._seen.clear()


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


def _status(
    state="OPEN",
    is_draft=False,
    author="pr-author",
    base_branch="feature/x",
    mergeable="MERGEABLE",
    merge_state="CLEAN",
):
    return PrStatus(
        state=state,
        is_draft=is_draft,
        author=author,
        base_branch=base_branch,
        mergeable=mergeable,
        merge_state=merge_state,
    )


def test_open_pr_approves_merges_replies_and_reacts():
    with (
        patch.object(handler, "get_pr_status", return_value=_status()),
        patch.object(handler, "approve_and_merge", return_value="bot-one") as merge,
        patch.object(handler, "post_message") as post,
        patch.object(handler, "add_reaction") as react,
    ):
        handler.handle_chat_event(_event(URL))

    merge.assert_called_once_with(URL, "pr-author")
    post.assert_called_once_with("✅ *Approved & merged!* Approved by bot-one, branch deleted. 🎉", THREAD)
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


def test_message_without_pr_url_replies_no_link_and_reacts():
    with (
        patch.object(handler, "get_pr_status") as status,
        patch.object(handler, "post_message") as post,
        patch.object(handler, "add_reaction") as react,
    ):
        handler.handle_chat_event(_event("good morning team"))

    status.assert_not_called()
    text, thread = post.call_args[0]
    assert "didn't spot a GitHub PR link" in text
    assert thread == THREAD
    post.assert_called_once()
    react.assert_called_once_with(MESSAGE, handler.EMOJI_NO_LINK)


def test_already_merged_reacts_noop_and_skips():
    with (
        patch.object(handler, "get_pr_status", return_value=_status(state="MERGED")),
        patch.object(handler, "approve_and_merge") as merge,
        patch.object(handler, "post_message") as post,
        patch.object(handler, "add_reaction") as react,
    ):
        handler.handle_chat_event(_event(URL))

    merge.assert_not_called()
    assert "already merged" in post.call_args[0][0]
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
    assert "couldn't find" in post.call_args[0][0]
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
    assert "couldn't approve" in text
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

    assert "merge didn't go through" in post.call_args[0][0]
    react.assert_called_once_with(MESSAGE, EMOJI_ATTENTION)


@pytest.mark.parametrize("branch", ["main", "master", "prezent", "Main", "PREZENT"])
def test_protected_base_branch_is_not_merged(branch):
    with (
        patch.object(handler, "get_pr_status", return_value=_status(base_branch=branch)),
        patch.object(handler, "approve_and_merge") as merge,
        patch.object(handler, "post_message") as post,
        patch.object(handler, "add_reaction") as react,
    ):
        handler.handle_chat_event(_event(URL))

    merge.assert_not_called()
    text = post.call_args[0][0]
    assert branch in text
    assert "not allowed to merge" in text
    react.assert_called_once_with(MESSAGE, EMOJI_ATTENTION)


@pytest.mark.parametrize(
    "mergeable,merge_state",
    [("CONFLICTING", "CLEAN"), ("MERGEABLE", "DIRTY"), ("CONFLICTING", "DIRTY")],
)
def test_conflicting_pr_declines_without_approving(mergeable, merge_state):
    with (
        patch.object(handler, "get_pr_status",
                     return_value=_status(mergeable=mergeable, merge_state=merge_state)),
        patch.object(handler, "approve_and_merge") as merge,
        patch.object(handler, "post_message") as post,
        patch.object(handler, "add_reaction") as react,
    ):
        handler.handle_chat_event(_event(URL))

    merge.assert_not_called()
    assert "merge conflicts" in post.call_args[0][0]
    react.assert_called_once_with(MESSAGE, EMOJI_ATTENTION)


def test_unknown_mergeability_still_approves():
    # GitHub may not have computed mergeability yet; UNKNOWN must NOT block approval.
    with (
        patch.object(handler, "get_pr_status",
                     return_value=_status(mergeable="UNKNOWN", merge_state="UNKNOWN")),
        patch.object(handler, "approve_and_merge", return_value="bot-one") as merge,
        patch.object(handler, "post_message"),
        patch.object(handler, "add_reaction"),
    ):
        handler.handle_chat_event(_event(URL))

    merge.assert_called_once_with(URL, "pr-author")


def test_duplicate_delivery_is_processed_once():
    # The same message id arriving twice (Pub/Sub at-least-once) must approve + merge only once.
    with (
        patch.object(handler, "get_pr_status", return_value=_status()),
        patch.object(handler, "approve_and_merge", return_value="bot-one") as merge,
        patch.object(handler, "post_message") as post,
        patch.object(handler, "add_reaction") as react,
    ):
        handler.handle_chat_event(_event(URL))
        handler.handle_chat_event(_event(URL))

    merge.assert_called_once_with(URL, "pr-author")
    post.assert_called_once()
    react.assert_called_once_with(MESSAGE, EMOJI_DONE)


def test_unexpected_error_still_replies_and_reacts():
    # A non-GhError exception (e.g. a bug) must still produce a thread reply, never a silent drop.
    with (
        patch.object(handler, "get_pr_status", side_effect=ValueError("boom")),
        patch.object(handler, "post_message") as post,
        patch.object(handler, "add_reaction") as react,
    ):
        handler.handle_chat_event(_event(URL))

    text, thread = post.call_args[0]
    assert "went wrong" in text
    assert thread == THREAD
    react.assert_called_once_with(MESSAGE, EMOJI_ATTENTION)
