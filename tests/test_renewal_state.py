import pytest

from review_pr import renewal_state

_THRESHOLD = 3 * 60 * 60


@pytest.fixture(autouse=True)
def _isolate_renewal(tmp_path, monkeypatch):
    """Point renewal_state at a temp file for each test."""
    monkeypatch.setattr(renewal_state, "_FILE", tmp_path / "last_renewal.json")
    yield


def test_load_missing_returns_none():
    assert renewal_state.load_last_renewal() is None


def test_corrupt_file_returns_none():
    renewal_state._FILE.write_text("{ not json")
    assert renewal_state.load_last_renewal() is None


def test_record_then_load_roundtrips():
    renewal_state.record_renewal(1719500880.5)
    assert renewal_state.load_last_renewal() == 1719500880.5


def test_state_survives_restart():
    renewal_state.record_renewal(1719500880.5)
    # A fresh load (as on restart) reads the value back from disk.
    assert renewal_state.load_last_renewal() == 1719500880.5


def test_should_renew_true_when_no_timestamp():
    assert renewal_state.should_renew(_THRESHOLD, now=1000.0) is True


def test_should_renew_false_within_threshold():
    renewal_state.record_renewal(1000.0)
    assert renewal_state.should_renew(_THRESHOLD, now=1000.0 + _THRESHOLD - 1) is False


def test_should_renew_true_at_threshold_boundary():
    renewal_state.record_renewal(1000.0)
    assert renewal_state.should_renew(_THRESHOLD, now=1000.0 + _THRESHOLD) is True


def test_record_failure_does_not_raise(monkeypatch):
    def _boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(renewal_state.Path, "mkdir", _boom)
    renewal_state.record_renewal(1000.0)  # no exception
    assert renewal_state.load_last_renewal() is None
