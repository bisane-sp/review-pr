import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

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


def test_singleton_lock_blocks_a_second_instance(tmp_path, monkeypatch):
    lock_file = tmp_path / "review-pr-bot.lock"
    monkeypatch.setattr(subscriber, "_LOCK_FILE", Path(lock_file))
    monkeypatch.setattr(subscriber, "_lock_handle", None)

    # First acquisition succeeds and holds the lock.
    subscriber._acquire_singleton_lock()
    first_handle = subscriber._lock_handle
    assert first_handle is not None

    # A second acquisition (separate fd, as a second process would do) cannot take the lock and exits.
    with pytest.raises(SystemExit) as exc:
        subscriber._acquire_singleton_lock()
    assert exc.value.code == 1

    # Release for other tests: close the second fd opened above, then the first.
    if subscriber._lock_handle is not None and subscriber._lock_handle is not first_handle:
        subscriber._lock_handle.close()
    first_handle.close()
    subscriber._lock_handle = None
