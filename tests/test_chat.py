from review_pr.chat import parse_message_event


def test_parse_workspace_events_message():
    # The real Workspace Events payload: no top-level "type", message carries sender/space/thread.
    payload = {
        "message": {
            "name": "spaces/AAAA/messages/M1",
            "text": "https://github.com/org/repo/pull/1",
            "sender": {"name": "users/123", "type": "HUMAN"},
            "thread": {"name": "spaces/AAAA/threads/T1"},
            "space": {"name": "spaces/AAAA"},
        }
    }
    event = parse_message_event(payload)
    assert event.event_type == ""  # Workspace Events payloads have no top-level type
    assert event.space_name == "spaces/AAAA"
    assert event.text == "https://github.com/org/repo/pull/1"
    assert event.thread_name == "spaces/AAAA/threads/T1"
    assert event.sender_type == "HUMAN"
    assert event.message_name == "spaces/AAAA/messages/M1"
    assert event.thread_reply is False  # top-level message: no threadReply key


def test_parse_thread_reply_flag():
    payload = {"message": {"text": "reply", "threadReply": True, "space": {"name": "spaces/AAAA"}}}
    event = parse_message_event(payload)
    assert event.thread_reply is True


def test_parse_falls_back_to_message_space():
    payload = {"message": {"space": {"name": "spaces/BBBB"}, "text": "hi"}}
    event = parse_message_event(payload)
    assert event.space_name == "spaces/BBBB"


def test_parse_bot_sender():
    payload = {"message": {"sender": {"type": "BOT"}, "text": "✅ Merged", "space": {"name": "spaces/AAAA"}}}
    event = parse_message_event(payload)
    assert event.sender_type == "BOT"


def test_parse_handles_missing_keys():
    event = parse_message_event({})
    assert event.event_type == ""
    assert event.space_name == ""
    assert event.text == ""
    assert event.thread_name is None
    assert event.thread_reply is False
    assert event.sender_type is None
    assert event.message_name is None
