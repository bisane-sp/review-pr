"""Extract a GitHub Pull Request URL from arbitrary message text."""

import re

PR_URL_RE = re.compile(r"https?://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/pull/\d+")


def extract_pr_urls(text: str) -> list[str]:
    """Return the unique GitHub PR URLs in ``text``, in order of first appearance."""
    return list(dict.fromkeys(PR_URL_RE.findall(text or "")))
