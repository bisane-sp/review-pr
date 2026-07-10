from unittest.mock import MagicMock, patch

from review_pr import reactions

MESSAGE = "spaces/AAAA/messages/M1"


def _creds(valid=True):
    return MagicMock(valid=valid, token="tok")


def test_add_reaction_posts_to_chat_api():
    response = MagicMock()
    response.json.return_value = {"name": f"{MESSAGE}/reactions/R1"}
    with (
        patch.object(reactions.Credentials, "from_authorized_user_file", return_value=_creds()),
        patch.object(reactions.requests, "post", return_value=response) as post,
    ):
        result = reactions.add_reaction(MESSAGE, "✅")

    post.assert_called_once()
    args, kwargs = post.call_args
    assert args[0] == f"https://chat.googleapis.com/v1/{MESSAGE}/reactions"
    assert kwargs["json"] == {"emoji": {"unicode": "✅"}}
    assert kwargs["headers"]["Authorization"] == "Bearer tok"
    response.raise_for_status.assert_called_once()
    assert result == f"{MESSAGE}/reactions/R1"


def test_add_reaction_refreshes_invalid_credentials():
    creds = _creds(valid=False)
    with (
        patch.object(reactions.Credentials, "from_authorized_user_file", return_value=creds),
        patch.object(reactions.requests, "post", return_value=MagicMock()),
    ):
        reactions.add_reaction(MESSAGE, "✅")

    creds.refresh.assert_called_once()


def test_add_reaction_swallows_errors():
    # A failed reaction must never raise (it would crash the subscriber callback).
    with patch.object(reactions.Credentials, "from_authorized_user_file", side_effect=FileNotFoundError()):
        assert reactions.add_reaction(MESSAGE, "✅") is None  # must not raise


REACTION = f"{MESSAGE}/reactions/R1"


def test_remove_reaction_deletes_via_chat_api():
    response = MagicMock()
    with (
        patch.object(reactions.Credentials, "from_authorized_user_file", return_value=_creds()),
        patch.object(reactions.requests, "delete", return_value=response) as delete,
    ):
        reactions.remove_reaction(REACTION)

    delete.assert_called_once()
    args, kwargs = delete.call_args
    assert args[0] == f"https://chat.googleapis.com/v1/{REACTION}"
    assert kwargs["headers"]["Authorization"] == "Bearer tok"
    response.raise_for_status.assert_called_once()


def test_remove_reaction_swallows_errors():
    # A failed removal must never raise (it would crash the subscriber callback).
    with patch.object(reactions.Credentials, "from_authorized_user_file", side_effect=FileNotFoundError()):
        reactions.remove_reaction(REACTION)  # must not raise
