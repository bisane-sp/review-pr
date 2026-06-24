import pytest

from review_pr.pr_url import extract_pr_url


@pytest.mark.parametrize(
    "text, expected",
    [
        ("https://github.com/org/repo/pull/123", "https://github.com/org/repo/pull/123"),
        ("please merge https://github.com/org/repo/pull/7 thanks", "https://github.com/org/repo/pull/7"),
        ("(https://github.com/org/repo/pull/42)", "https://github.com/org/repo/pull/42"),
        ("see https://github.com/org/repo/pull/42.", "https://github.com/org/repo/pull/42"),
        ("http://github.com/a/b/pull/1", "http://github.com/a/b/pull/1"),
        ("with.dots/and-dashes https://github.com/my-org/my.repo/pull/99", "https://github.com/my-org/my.repo/pull/99"),
        (
            "first https://github.com/org/repo/pull/1 second https://github.com/org/repo/pull/2",
            "https://github.com/org/repo/pull/1",
        ),
    ],
)
def test_extracts_pr_url(text, expected):
    assert extract_pr_url(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "",
        "no link here",
        "https://github.com/org/repo/issues/5",
        "https://gitlab.com/org/repo/pull/5",
        "https://github.com/org/repo/pull/",
        "just talking about a pull request",
    ],
)
def test_returns_none_when_no_pr_url(text):
    assert extract_pr_url(text) is None
