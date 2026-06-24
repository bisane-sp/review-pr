import json
import subprocess
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from review_pr import github
from review_pr.github import GhError, approve_and_merge, get_pr_status

URL = "https://github.com/org/repo/pull/1"


def _ok(stdout=""):
    return MagicMock(returncode=0, stdout=stdout, stderr="")


def _fail(stderr):
    return MagicMock(returncode=1, stdout="", stderr=stderr)


def _status_json(
    state="OPEN",
    is_draft=False,
    author="pr-author",
    base_branch="feature/x",
    mergeable="MERGEABLE",
    merge_state="CLEAN",
):
    return json.dumps(
        {
            "state": state,
            "isDraft": is_draft,
            "author": {"login": author},
            "baseRefName": base_branch,
            "mergeable": mergeable,
            "mergeStateStatus": merge_state,
        }
    )


# --- get_pr_status ---------------------------------------------------------


def test_get_pr_status_parses_fields():
    with patch.object(github.subprocess, "run", side_effect=[_ok(_status_json(state="OPEN", author="alice"))]) as run:
        status = get_pr_status(URL)

    assert status.state == "OPEN"
    assert status.is_draft is False
    assert status.author == "alice"
    assert status.base_branch == "feature/x"
    assert status.mergeable == "MERGEABLE"
    assert status.merge_state == "CLEAN"
    args = run.call_args_list[0][0][0]
    assert args == ["gh", "pr", "view", URL, "--json", "state,isDraft,author,baseRefName,mergeable,mergeStateStatus"]
    assert run.call_args_list[0][1]["env"]["GH_TOKEN"] == "token-1"  # lookup uses first account


def test_get_pr_status_lookup_failure_raises():
    with patch.object(github.subprocess, "run", side_effect=[_fail("not found")]):
        with pytest.raises(GhError) as exc:
            get_pr_status(URL)
    assert exc.value.step == "lookup"


def test_get_pr_status_timeout_raises():
    with patch.object(github.subprocess, "run", side_effect=subprocess.TimeoutExpired("gh", 5)):
        with pytest.raises(GhError) as exc:
            get_pr_status(URL)
    assert exc.value.step == "lookup"


def test_get_pr_status_missing_gh_raises():
    with patch.object(github.subprocess, "run", side_effect=FileNotFoundError()):
        with pytest.raises(GhError) as exc:
            get_pr_status(URL)
    assert "not found" in exc.value.message


# --- subprocess environment ------------------------------------------------


def test_blank_token_refuses_to_run_gh():
    # A blank token must never reach gh, or gh would fall back to the local terminal login.
    with patch.object(github.subprocess, "run") as run:
        with pytest.raises(GhError) as exc:
            github._run_gh(["gh", "api", "user"], "lookup", "   ")
    assert exc.value.step == "lookup"
    assert run.call_count == 0  # gh never invoked


def test_gh_env_passes_token_but_not_unrelated_secrets(monkeypatch):
    # An unrelated secret in the parent env must NOT reach the gh subprocess.
    monkeypatch.setenv("UNRELATED_SECRET", "do-not-leak")
    monkeypatch.setenv("PATH", "/usr/bin")
    with patch.object(github.subprocess, "run", side_effect=[_ok(_status_json())]) as run:
        get_pr_status(URL)

    env = run.call_args_list[0][1]["env"]
    assert env["GH_TOKEN"] == "token-1"
    assert env["PATH"] == "/usr/bin"  # passthrough var forwarded
    assert "UNRELATED_SECRET" not in env  # everything else dropped


# --- approve_and_merge -----------------------------------------------------


def test_approves_with_first_account_when_author_is_neither():
    # author "pr-author" is neither configured account -> first account (bot-one) approves.
    with patch.object(github.subprocess, "run", side_effect=[_ok(), _ok()]) as run:
        account = approve_and_merge(URL, "pr-author")

    assert account == "bot-one"
    assert run.call_count == 2  # review + merge, no lookup
    review_args, review_kwargs = run.call_args_list[0]
    merge_args, merge_kwargs = run.call_args_list[1]

    assert review_args[0] == ["gh", "pr", "review", URL, "--approve", "--body", ""]
    assert merge_args[0] == ["gh", "pr", "merge", URL, "--merge", "--delete-branch"]
    assert review_kwargs["env"]["GH_TOKEN"] == "token-1"
    assert merge_kwargs["env"]["GH_TOKEN"] == "token-1"


def test_uses_second_account_when_first_is_the_author():
    # author == bot-one -> must approve with bot-two's token.
    with patch.object(github.subprocess, "run", side_effect=[_ok(), _ok()]) as run:
        account = approve_and_merge(URL, "bot-one")

    assert account == "bot-two"
    assert run.call_args_list[0][1]["env"]["GH_TOKEN"] == "token-2"
    assert run.call_args_list[1][1]["env"]["GH_TOKEN"] == "token-2"


def test_merge_not_attempted_when_approve_fails():
    with patch.object(github.subprocess, "run", side_effect=[_fail("no perms")]) as run:
        with pytest.raises(GhError) as exc:
            approve_and_merge(URL, "pr-author")

    assert exc.value.step == "approve"
    assert run.call_count == 1  # failed review, no merge


def test_merge_failure_raises_with_merge_step():
    with patch.object(github.subprocess, "run", side_effect=[_ok(), _fail("blocked")]) as run:
        with pytest.raises(GhError) as exc:
            approve_and_merge(URL, "pr-author")

    assert exc.value.step == "merge"
    assert "blocked" in exc.value.message
    assert run.call_count == 2


def test_select_account_raises_when_all_accounts_are_author(monkeypatch):
    dummy = SimpleNamespace(github_accounts=[("bot", "t1"), ("bot", "t2")])
    monkeypatch.setattr(github, "settings", dummy)
    with pytest.raises(GhError) as exc:
        github._select_account("bot")
    assert exc.value.step == "approve"
