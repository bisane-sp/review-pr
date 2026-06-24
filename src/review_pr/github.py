"""Approve and merge a GitHub PR via the ``gh`` CLI.

GitHub forbids approving your own PR, so we configure two accounts and approve with whichever one
is NOT the PR's author.
"""

import json
import os
import subprocess
from dataclasses import dataclass

from .config import settings

_STDERR_LIMIT = 500


class GhError(Exception):
    """A ``gh`` command failed. ``step`` is ``"lookup"``, ``"approve"`` or ``"merge"``."""

    def __init__(self, step: str, message: str):
        self.step = step
        self.message = message
        super().__init__(f"{step}: {message}")


def _run_gh(args: list[str], step: str, token: str) -> str:
    """Run a ``gh`` command with ``token`` injected via env. Raise ``GhError`` on any failure.

    Returns the command's stripped stdout.
    """
    env = {**os.environ, "GH_TOKEN": token}
    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=settings.gh_timeout_seconds,
            env=env,
        )
    except subprocess.TimeoutExpired:
        raise GhError(step, f"timed out after {settings.gh_timeout_seconds}s")
    except FileNotFoundError:
        raise GhError(step, "gh CLI not found on PATH")

    if result.returncode != 0:
        raise GhError(step, (result.stderr or result.stdout or "").strip()[:_STDERR_LIMIT])
    return result.stdout.strip()


@dataclass
class PrStatus:
    """The PR fields we branch on before deciding whether to approve + merge."""

    state: str  # "OPEN" | "CLOSED" | "MERGED"
    is_draft: bool
    author: str
    base_branch: str  # baseRefName: the branch the PR would merge into
    mergeable: str  # "MERGEABLE" | "CONFLICTING" | "UNKNOWN"
    merge_state: str  # mergeStateStatus: "CLEAN" | "BLOCKED" | "DIRTY" | "UNSTABLE" | ...


def get_pr_status(url: str) -> PrStatus:
    """Look up the PR's state, draft flag, author and mergeability. Any configured token can read this.

    Raises ``GhError`` with ``step="lookup"`` if the PR can't be read.
    """
    _, token = settings.github_accounts[0]
    out = _run_gh(
        ["gh", "pr", "view", url, "--json", "state,isDraft,author,baseRefName,mergeable,mergeStateStatus"],
        "lookup",
        token,
    )
    try:
        data = json.loads(out)
    except json.JSONDecodeError as exc:
        raise GhError("lookup", f"could not parse PR data: {exc}")
    return PrStatus(
        state=data.get("state", ""),
        is_draft=data.get("isDraft", False),
        author=(data.get("author") or {}).get("login", ""),
        base_branch=data.get("baseRefName", ""),
        mergeable=data.get("mergeable", ""),
        merge_state=data.get("mergeStateStatus", ""),
    )


def _select_account(author: str) -> tuple[str, str]:
    """Return the first configured (account, token) whose login is not ``author``."""
    for account, token in settings.github_accounts:
        if account != author:
            return account, token
    raise GhError("approve", f"no configured account can approve a PR authored by {author}")


def approve_and_merge(url: str, author: str) -> str:
    """Approve the PR (with a non-author account) then merge it. Returns the approving account.

    Raises ``GhError`` with ``step`` of ``"approve"`` or ``"merge"`` on failure.
    """
    account, token = _select_account(author)
    _run_gh(["gh", "pr", "review", url, "--approve", "--body", "lgtm."], "approve", token)
    _run_gh(["gh", "pr", "merge", url, "--merge", "--delete-branch"], "merge", token)
    return account
