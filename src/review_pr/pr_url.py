"""Extract a GitHub Pull Request URL from arbitrary message text."""

import re

PR_URL_RE = re.compile(r"https?://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/pull/\d+")


def extract_pr_url(text: str) -> str | None:
    """Return the first GitHub PR URL found in ``text``, or ``None`` if there is none."""
    match = PR_URL_RE.search(text or "")
    return match.group(0) if match else None
