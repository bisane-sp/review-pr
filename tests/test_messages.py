from review_pr.messages import friendly_gh_error


def test_self_approve_is_translated_and_hides_raw():
    raw = "failed to create review: GraphQL: Review Can not approve your own pull request (addPullRequestReview)"
    text = friendly_gh_error("approve", raw)
    assert "can't approve" in text
    assert "GraphQL" not in text
    assert "addPullRequestReview" not in text


def test_no_configured_account_is_self_approve():
    text = friendly_gh_error("approve", "no configured account can approve a PR authored by alice")
    assert "can't approve" in text


def test_merge_conflict():
    text = friendly_gh_error("merge", "Pull request is not mergeable: the merge commit cannot be cleanly created")
    assert "merge conflicts" in text
    assert "not mergeable" not in text


def test_branch_protection_block():
    text = friendly_gh_error("merge", "GraphQL: Required status check is expected (mergePullRequest)")
    assert "blocking the merge" in text


def test_lookup_not_found():
    text = friendly_gh_error("lookup", "GraphQL: Could not resolve to a PullRequest (HTTP 404)")
    assert "couldn't find" in text


def test_auth_error_any_step():
    text = friendly_gh_error("lookup", "HTTP 401: Bad credentials")
    assert "permission" in text


def test_timeout_any_step():
    text = friendly_gh_error("approve", "timed out after 60s")
    assert "took too long" in text


def test_generic_fallback_per_step_hides_raw():
    raw = "some totally unexpected gh failure blob"
    assert "couldn't read" in friendly_gh_error("lookup", raw)
    assert "didn't go through" in friendly_gh_error("merge", raw)
    assert "couldn't approve" in friendly_gh_error("approve", raw)
    for step in ("lookup", "merge", "approve"):
        assert raw not in friendly_gh_error(step, raw)


def test_no_reply_contains_a_url():
    cases = [
        ("approve", "Can not approve your own pull request"),
        ("merge", "not mergeable"),
        ("merge", "branch protection"),
        ("lookup", "HTTP 404 not found"),
        ("lookup", "Bad credentials"),
        ("approve", "timed out after 60s"),
        ("merge", "unrecognised blob"),
    ]
    for step, raw in cases:
        assert "http" not in friendly_gh_error(step, raw).lower()
