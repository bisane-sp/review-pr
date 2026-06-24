from review_pr.config import Settings


def test_blank_second_account_is_dropped(monkeypatch):
    # An unconfigured second account must be absent, not a blank pair that would let gh fall back
    # to the machine's logged-in user.
    monkeypatch.setenv("GITHUB_ACCOUNT_2", "")
    monkeypatch.setenv("GITHUB_TOKEN_2", "  ")
    assert Settings().github_accounts == [("bot-one", "token-1")]


def test_both_accounts_kept_when_configured(monkeypatch):
    monkeypatch.setenv("GITHUB_ACCOUNT_2", "bot-two")
    monkeypatch.setenv("GITHUB_TOKEN_2", "token-2")
    assert Settings().github_accounts == [("bot-one", "token-1"), ("bot-two", "token-2")]
