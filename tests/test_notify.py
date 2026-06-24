from unittest.mock import patch

from review_pr import notify
from review_pr.notify import post_message

WEBHOOK = "https://chat.example/webhook?key=k&token=t"


def test_post_message_without_thread():
    with patch.object(notify.requests, "post") as post:
        post_message("hello")

    args, kwargs = post.call_args
    assert args[0] == WEBHOOK
    assert kwargs["json"] == {"text": "hello"}
    assert kwargs["params"] == {}


def test_post_message_with_thread_sets_reply_option():
    with patch.object(notify.requests, "post") as post:
        post_message("done", "spaces/TEST/threads/T1")

    _, kwargs = post.call_args
    assert kwargs["json"] == {"text": "done", "thread": {"name": "spaces/TEST/threads/T1"}}
    assert kwargs["params"] == {"messageReplyOption": "REPLY_MESSAGE_FALLBACK_TO_NEW_THREAD"}


def test_post_message_swallows_request_errors():
    import requests

    with patch.object(notify.requests, "post", side_effect=requests.RequestException("boom")):
        # Should not raise — a failed notification must not crash the subscriber.
        post_message("hello")
