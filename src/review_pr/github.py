"""Approve and merge a GitHub PR via the ``gh`` CLI.

GitHub forbids approving your own PR, so we configure two accounts and approve with whichever one
is NOT the PR's author.
"""

import json
import logging
import os
import subprocess
from dataclasses import dataclass

from .config import settings

logger = logging.getLogger(__name__)

_STDERR_LIMIT = 500

# Parent env vars forwarded to the gh subprocess. Everything else (other secrets in os.environ) is
# dropped so only GH_TOKEN and what gh needs to run and reach GitHub is exposed to the child process.
_ENV_PASSTHROUGH = ("PATH", "HOME", "GH_CONFIG_DIR", "HTTPS_PROXY", "HTTP_PROXY", "NO_PROXY")


class GhError(Exception):
    """A ``gh`` command failed. ``step`` is ``"lookup"``, ``"approve"`` or ``"merge"``."""

    def __init__(self, step: str, message: str):
        self.step = step
        self.message = message
        super().__init__(f"{step}: {message}")


def _gh_env(token: str) -> dict[str, str]:
    """Build a minimal environment for a ``gh`` subprocess: ``GH_TOKEN`` plus a few passthrough vars.

    Avoids handing the whole parent environment (and any other secrets it holds) to the child.
    """
    env = {"GH_TOKEN": token}
    for key in _ENV_PASSTHROUGH:
        value = os.environ.get(key)
        if value is not None:
            env[key] = value
    return env


def _run_gh(args: list[str], step: str, token: str) -> str:
    """Run a ``gh`` command with ``token`` injected via env. Raise ``GhError`` on any failure.

    Returns the command's stripped stdout.
    """
    # A blank GH_TOKEN makes gh silently fall back to the locally logged-in account. Refuse to run
    # rather than act as whatever account happens to be logged in on this machine.
    if not token.strip():
        raise GhError(step, "no GitHub token configured for this account (refusing to use local gh login)")
    env = _gh_env(token)
    logger.debug("gh %s: running %s", step, " ".join(args))  # token is in env, never in args
    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=settings.gh_timeout_seconds,
            env=env,
        )
    except subprocess.TimeoutExpired:
        logger.debug("gh %s: timed out after %ss", step, settings.gh_timeout_seconds)
        raise GhError(step, f"timed out after {settings.gh_timeout_seconds}s")
    except FileNotFoundError:
        logger.debug("gh %s: gh CLI not found on PATH", step)
        raise GhError(step, "gh CLI not found on PATH")

    logger.debug(
        "gh %s: rc=%s stdout=%r stderr=%r",
        step,
        result.returncode,
        result.stdout.strip()[:_STDERR_LIMIT],
        result.stderr.strip()[:_STDERR_LIMIT],
    )
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
    accounts = settings.github_accounts
    if not accounts:
        raise GhError("lookup", "no GitHub account configured")
    _, token = accounts[0]
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
    _run_gh(["gh", "pr", "review", url, "--approve", "--body", ""], "approve", token)
    _run_gh(["gh", "pr", "merge", url, "--merge", "--delete-branch"], "merge", token)
    return account
