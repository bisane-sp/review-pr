import json
from unittest.mock import MagicMock, patch

from review_pr import subscriber


def test_callback_decodes_payload_handles_and_acks():
    payload = {"type": "MESSAGE", "space": {"name": "spaces/TEST"}, "message": {"text": "hi"}}
    message = MagicMock(data=json.dumps(payload).encode())

    with patch.object(subscriber, "handle_chat_event") as handle:
        subscriber._callback(message)

    handle.assert_called_once_with(payload)
    message.ack.assert_called_once()


def test_callback_acks_even_when_handling_fails():
    message = MagicMock(data=b"not-json")

    with patch.object(subscriber, "handle_chat_event") as handle:
        subscriber._callback(message)

    handle.assert_not_called()
    message.ack.assert_called_once()
