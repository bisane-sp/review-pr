import json

import pytest

from review_pr import dedup


@pytest.fixture(autouse=True)
def _isolate_dedup(tmp_path, monkeypatch):
    """Point dedup at a temp file and start each test with empty, unloaded state."""
    monkeypatch.setattr(dedup, "_DEDUP_FILE", tmp_path / "dedup.json")
    dedup._seen.clear()
    monkeypatch.setattr(dedup, "_loaded", False)
    yield
    dedup._seen.clear()


def test_first_claim_true_second_false():
    assert dedup.claim("spaces/X/messages/1") is True
    assert dedup.claim("spaces/X/messages/1") is False


def test_claim_writes_file():
    dedup.claim("spaces/X/messages/1")
    assert dedup._DEDUP_FILE.exists()
    assert "spaces/X/messages/1" in dedup._DEDUP_FILE.read_text()


def test_state_survives_restart():
    dedup.claim("spaces/X/messages/1")
    # Simulate a restart: wipe in-memory state, force a reload from disk.
    dedup._seen.clear()
    dedup._loaded = False
    assert dedup.claim("spaces/X/messages/1") is False


def test_corrupt_file_starts_empty():
    dedup._DEDUP_FILE.write_text("{ not json")
    assert dedup.claim("spaces/X/messages/1") is True


def test_save_failure_does_not_raise(monkeypatch):
    # A persistence failure must not break claim() — claim is called outside the handler's
    # try/except, so a raised OSError would skip the user's reply/reaction.
    def _boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(dedup.Path, "mkdir", _boom)
    assert dedup.claim("spaces/X/messages/1") is True   # no exception
    assert dedup.claim("spaces/X/messages/1") is False  # in-memory dedup still works


def test_bound_is_enforced_and_mirrored(monkeypatch):
    monkeypatch.setattr(dedup, "_MAX_REMEMBERED", 3)
    for i in range(4):
        dedup.claim(f"m{i}")
    saved = json.loads(dedup._DEDUP_FILE.read_text())
    assert saved == ["m1", "m2", "m3"]  # oldest (m0) dropped
    assert dedup.claim("m0") is True    # m0 no longer remembered
