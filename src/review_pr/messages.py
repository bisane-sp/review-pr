"""Translate raw ``gh`` CLI errors into plain-English Google Chat replies.

The raw CLI/GraphQL text is technical and confusing for non-developers, so we map the failures we
expect to friendly messages with a next step. The raw text is never shown to the user — it is logged
by the caller. Unrecognised failures fall back to a per-step generic message. Replies are posted in
the PR link's thread, so they never repeat the URL.
"""

# Ordered rules: the first whose ``step`` matches (or "any") and whose any substring appears
# (case-insensitive) in the raw message wins.
_RULES: list[tuple[str, tuple[str, ...], str]] = [
    (
        "approve",
        ("can not approve your own", "no configured account can approve"),
        "❌ I can't approve this PR — GitHub won't let an account approve its own pull request. "
        "Ask a teammate to send it instead.",
    ),
    (
        "merge",
        ("not mergeable", "conflict"),
        "⚠️ I approved this PR, but it has merge conflicts. Please resolve them and resend the link.",
    ),
    (
        "merge",
        ("branch protection", "required", "review", "checks", "not authorized"),
        "⚠️ I approved this PR, but GitHub is blocking the merge (branch protection or pending "
        "checks). It'll go through once the requirements pass.",
    ),
    (
        "lookup",
        ("no github account configured",),
        "❌ I don't have GitHub account credentials configured to approve and merge this PR. "
        "Please set them up first.",
    ),
    (
        "lookup",
        ("not found", "404", "could not resolve", "no such"),
        "❌ I couldn't find this PR or I don't have access. Check the link and that I'm added to the "
        "repo.",
    ),
    (
        "any",
        ("bad credentials", "401", "403"),
        "🔒 I don't have permission for this PR. My GitHub access may need refreshing.",
    ),
    (
        "any",
        ("timed out",),
        "⏳ GitHub took too long to respond. Please try again.",
    ),
]

_GENERIC = {
    "lookup": "❌ I couldn't read this PR right now. Please try again shortly.",
    "merge": "⚠️ I approved this PR, but the merge didn't go through. Please check it.",
    "approve": "❌ I couldn't approve this PR. Please check it and try again.",
}


def friendly_gh_error(step: str, raw: str) -> str:
    """Map a raw ``gh`` error to a plain-English reply. Raw text is NOT included (logs only)."""
    lowered = (raw or "").lower()
    for rule_step, substrings, template in _RULES:
        if rule_step in (step, "any") and any(s in lowered for s in substrings):
            return template
    return _GENERIC.get(step, _GENERIC["approve"])
