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
def _clear_dedup(tmp_path, monkeypatch):
    """Reset the dedup history (and redirect its file) so each test's message id is fresh."""
    monkeypatch.setattr(dedup, "_DEDUP_FILE", tmp_path / "dedup.json")
    dedup._seen.clear()
    monkeypatch.setattr(dedup, "_loaded", True)  # empty + loaded: no read of the real file
    yield
    dedup._seen.clear()


def _event(text, space=SPACE, thread=THREAD, sender_type="HUMAN", message_name=MESSAGE, thread_reply=False):
    """A Workspace Events message payload (no top-level "type")."""
    message = {
        "name": message_name,
        "text": text,
        "thread": {"name": thread},
        "sender": {"type": sender_type},
    }
    if thread_reply:
        message["threadReply"] = True
    return {"space": {"name": space}, "message": message}


def _status(
    state="OPEN",
    is_draft=False,
    author="pr-author",
    base_branch="feature/x",
    mergeable="MERGEABLE",
    merge_state="CLEAN",
    merged_by="",
):
    return PrStatus(
        state=state,
        is_draft=is_draft,
        author=author,
        base_branch=base_branch,
        mergeable=mergeable,
        merge_state=merge_state,
        merged_by=merged_by,
    )


def test_open_pr_approves_merges_replies_and_reacts():
    with (
        patch.object(handler, "get_pr_status", return_value=_status()),
        patch.object(handler, "approve_and_merge", return_value="bot-one") as merge,
        patch.object(handler, "post_message") as post,
        patch.object(handler, "add_reaction", return_value="reaction/R1") as react,
        patch.object(handler, "remove_reaction") as unreact,
    ):
        handler.handle_chat_event(_event(URL))

    merge.assert_called_once_with(URL, "pr-author")
    # An immediate ack reply, then the final outcome reply — both in-thread.
    assert post.call_args_list[0][0] == ("👀 On it — looking into this PR now…", THREAD)
    assert post.call_args_list[-1][0] == ("✅ *Approved & merged!* Approved by bot-one, branch deleted. 🎉", THREAD)
    # 👀 added on receipt, removed, then replaced by the outcome emoji.
    assert react.call_args_list[0][0] == (MESSAGE, handler.EMOJI_WORKING)
    unreact.assert_called_once_with("reaction/R1")
    assert react.call_args_list[-1][0] == (MESSAGE, EMOJI_DONE)


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


def test_thread_reply_message_is_ignored():
    # Replies inside a thread are skipped entirely, even with a valid PR link: no lookup/reply/react.
    with (
        patch.object(handler, "get_pr_status") as status,
        patch.object(handler, "approve_and_merge") as merge,
        patch.object(handler, "post_message") as post,
        patch.object(handler, "add_reaction") as react,
    ):
        handler.handle_chat_event(_event(URL, thread_reply=True))

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


def test_multiple_pr_links_replies_and_takes_no_action():
    # More than one distinct PR link is ambiguous: reply, react, and never touch gh.
    second = "https://github.com/org/repo/pull/2"
    with (
        patch.object(handler, "get_pr_status") as status,
        patch.object(handler, "approve_and_merge") as merge,
        patch.object(handler, "post_message") as post,
        patch.object(handler, "add_reaction") as react,
    ):
        handler.handle_chat_event(_event(f"merge {URL} and {second}"))

    status.assert_not_called()
    merge.assert_not_called()
    text, thread = post.call_args[0]
    assert "more than one PR link" in text
    assert thread == THREAD
    post.assert_called_once()
    react.assert_called_once_with(MESSAGE, handler.EMOJI_MULTI)


def test_same_pr_link_twice_is_processed_once():
    # A duplicate of the same URL counts as one link and is still approved + merged.
    with (
        patch.object(handler, "get_pr_status", return_value=_status()),
        patch.object(handler, "approve_and_merge", return_value="bot-one") as merge,
        patch.object(handler, "post_message") as post,
        patch.object(handler, "add_reaction") as react,
        patch.object(handler, "remove_reaction"),
    ):
        handler.handle_chat_event(_event(f"{URL} {URL}"))

    merge.assert_called_once_with(URL, "pr-author")
    post.assert_called_with("✅ *Approved & merged!* Approved by bot-one, branch deleted. 🎉", THREAD)
    react.assert_called_with(MESSAGE, EMOJI_DONE)


def test_already_merged_reacts_noop_and_skips():
    with (
        patch.object(handler, "get_pr_status", return_value=_status(state="MERGED")),
        patch.object(handler, "approve_and_merge") as merge,
        patch.object(handler, "post_message") as post,
        patch.object(handler, "add_reaction") as react,
        patch.object(handler, "remove_reaction"),
    ):
        handler.handle_chat_event(_event(URL))

    merge.assert_not_called()
    assert "already merged" in post.call_args[0][0]
    react.assert_called_with(MESSAGE, EMOJI_NOOP)


def test_closed_pr_reacts_attention_and_skips():
    with (
        patch.object(handler, "get_pr_status", return_value=_status(state="CLOSED")),
        patch.object(handler, "approve_and_merge") as merge,
        patch.object(handler, "post_message") as post,
        patch.object(handler, "add_reaction") as react,
        patch.object(handler, "remove_reaction"),
    ):
        handler.handle_chat_event(_event(URL))

    merge.assert_not_called()
    assert "closed" in post.call_args[0][0]
    react.assert_called_with(MESSAGE, EMOJI_ATTENTION)


def test_draft_pr_reacts_attention_and_skips():
    with (
        patch.object(handler, "get_pr_status", return_value=_status(is_draft=True)),
        patch.object(handler, "approve_and_merge") as merge,
        patch.object(handler, "post_message") as post,
        patch.object(handler, "add_reaction") as react,
        patch.object(handler, "remove_reaction"),
    ):
        handler.handle_chat_event(_event(URL))

    merge.assert_not_called()
    assert "draft" in post.call_args[0][0]
    react.assert_called_with(MESSAGE, EMOJI_ATTENTION)


def test_lookup_failure_reacts_attention_and_replies():
    with (
        patch.object(handler, "get_pr_status", side_effect=GhError("lookup", "not found")),
        patch.object(handler, "approve_and_merge") as merge,
        patch.object(handler, "post_message") as post,
        patch.object(handler, "add_reaction") as react,
        patch.object(handler, "remove_reaction"),
    ):
        handler.handle_chat_event(_event(URL))

    merge.assert_not_called()
    assert "couldn't find" in post.call_args[0][0]
    react.assert_called_with(MESSAGE, EMOJI_ATTENTION)


def test_approve_failure_reacts_attention_and_replies():
    with (
        patch.object(handler, "get_pr_status", return_value=_status()),
        patch.object(handler, "approve_and_merge", side_effect=GhError("approve", "no perms")),
        patch.object(handler, "post_message") as post,
        patch.object(handler, "add_reaction") as react,
        patch.object(handler, "remove_reaction"),
    ):
        handler.handle_chat_event(_event(URL))

    text, thread = post.call_args[0]
    assert "couldn't approve" in text
    assert thread == THREAD
    react.assert_called_with(MESSAGE, EMOJI_ATTENTION)


def test_merge_failure_reacts_attention_and_replies():
    with (
        patch.object(handler, "get_pr_status", return_value=_status()),
        patch.object(handler, "approve_and_merge", side_effect=GhError("merge", "blocked")),
        patch.object(handler, "post_message") as post,
        patch.object(handler, "add_reaction") as react,
        patch.object(handler, "remove_reaction"),
    ):
        handler.handle_chat_event(_event(URL))

    assert "merge didn't go through" in post.call_args[0][0]
    react.assert_called_with(MESSAGE, EMOJI_ATTENTION)


def test_merge_command_fails_but_pr_already_merged_is_noop():
    # Race: the merge CLI command fails because a human merged on the web first. Re-reading shows the
    # PR is merged, so this is a no-op for us — not the "merge didn't go through" error.
    with (
        patch.object(handler, "get_pr_status", side_effect=[_status(), _status(state="MERGED")]),
        patch.object(handler, "approve_and_merge", side_effect=GhError("merge", "not in the correct state")),
        patch.object(handler, "post_message") as post,
        patch.object(handler, "add_reaction") as react,
        patch.object(handler, "remove_reaction"),
    ):
        handler.handle_chat_event(_event(URL))

    assert "already merged" in post.call_args[0][0]
    react.assert_called_with(MESSAGE, EMOJI_NOOP)


def test_merge_succeeds_but_human_merged_does_not_take_credit():
    # The merge command returns, but GitHub names a non-bot merger (web/bot race) — reply neutrally
    # instead of claiming "Approved & merged".
    with (
        patch.object(handler, "get_pr_status", side_effect=[_status(), _status(state="MERGED", merged_by="someone")]),
        patch.object(handler, "approve_and_merge", return_value="bot-one") as merge,
        patch.object(handler, "post_message") as post,
        patch.object(handler, "add_reaction") as react,
        patch.object(handler, "remove_reaction"),
    ):
        handler.handle_chat_event(_event(URL))

    merge.assert_called_once_with(URL, "pr-author")
    assert "already merged" in post.call_args[0][0]
    react.assert_called_with(MESSAGE, EMOJI_NOOP)


def test_merge_succeeds_by_bot_account_takes_credit():
    # The merge command returns and GitHub confirms a configured bot account merged it — take credit.
    with (
        patch.object(handler, "get_pr_status", side_effect=[_status(), _status(state="MERGED", merged_by="bot-one")]),
        patch.object(handler, "approve_and_merge", return_value="bot-one") as merge,
        patch.object(handler, "post_message") as post,
        patch.object(handler, "add_reaction") as react,
        patch.object(handler, "remove_reaction"),
    ):
        handler.handle_chat_event(_event(URL))

    merge.assert_called_once_with(URL, "pr-author")
    post.assert_called_with("✅ *Approved & merged!* Approved by bot-one, branch deleted. 🎉", THREAD)
    react.assert_called_with(MESSAGE, EMOJI_DONE)


@pytest.mark.parametrize("branch", ["main", "master", "prezent", "Main", "PREZENT"])
def test_protected_base_branch_is_not_merged(branch):
    with (
        patch.object(handler, "get_pr_status", return_value=_status(base_branch=branch)),
        patch.object(handler, "approve_and_merge") as merge,
        patch.object(handler, "post_message") as post,
        patch.object(handler, "add_reaction") as react,
        patch.object(handler, "remove_reaction"),
    ):
        handler.handle_chat_event(_event(URL))

    merge.assert_not_called()
    text = post.call_args[0][0]
    assert branch in text
    assert "not allowed to merge" in text
    react.assert_called_with(MESSAGE, EMOJI_ATTENTION)


@pytest.mark.parametrize(
    "mergeable,merge_state",
    [("CONFLICTING", "CLEAN"), ("MERGEABLE", "DIRTY"), ("CONFLICTING", "DIRTY")],
)
def test_conflicting_pr_declines_without_approving(mergeable, merge_state):
    with (
        patch.object(handler, "get_pr_status", return_value=_status(mergeable=mergeable, merge_state=merge_state)),
        patch.object(handler, "approve_and_merge") as merge,
        patch.object(handler, "post_message") as post,
        patch.object(handler, "add_reaction") as react,
        patch.object(handler, "remove_reaction"),
    ):
        handler.handle_chat_event(_event(URL))

    merge.assert_not_called()
    text, thread = post.call_args[0]
    assert "merge conflicts" in text
    assert thread == THREAD
    react.assert_called_with(MESSAGE, EMOJI_ATTENTION)


def test_unknown_mergeability_still_approves():
    # GitHub may not have computed mergeability yet; UNKNOWN must NOT block approval.
    with (
        patch.object(handler, "get_pr_status", return_value=_status(mergeable="UNKNOWN", merge_state="UNKNOWN")),
        patch.object(handler, "approve_and_merge", return_value="bot-one") as merge,
        patch.object(handler, "post_message"),
        patch.object(handler, "add_reaction"),
        patch.object(handler, "remove_reaction"),
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
        patch.object(handler, "remove_reaction"),
    ):
        handler.handle_chat_event(_event(URL))
        handler.handle_chat_event(_event(URL))

    merge.assert_called_once_with(URL, "pr-author")
    # Processed once: ack reply + outcome reply (the redelivery is deduped away).
    assert post.call_count == 2
    react.assert_called_with(MESSAGE, EMOJI_DONE)


def test_unexpected_error_still_replies_and_reacts():
    # A non-GhError exception (e.g. a bug) must still produce a thread reply, never a silent drop.
    with (
        patch.object(handler, "get_pr_status", side_effect=ValueError("boom")),
        patch.object(handler, "post_message") as post,
        patch.object(handler, "add_reaction") as react,
        patch.object(handler, "remove_reaction"),
    ):
        handler.handle_chat_event(_event(URL))

    text, thread = post.call_args[0]
    assert "went wrong" in text
    assert thread == THREAD
    react.assert_called_with(MESSAGE, EMOJI_ATTENTION)
