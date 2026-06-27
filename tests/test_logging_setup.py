import os
import time

from review_pr import logging_setup


def _make_log(dir_path, name, age_days):
    path = dir_path / name
    path.write_text("x")
    old = time.time() - age_days * 86400
    os.utime(path, (old, old))
    return path


def test_prune_removes_old_keeps_recent_and_active(tmp_path, monkeypatch):
    monkeypatch.setattr(logging_setup, "LOG_DIR", tmp_path)
    monkeypatch.setattr(logging_setup, "RETENTION_DAYS", 7)

    old = _make_log(tmp_path, "review-pr_2020-01-01_00-00-00.log", age_days=30)
    recent = _make_log(tmp_path, "review-pr_2026-06-20_00-00-00.log", age_days=1)
    active = _make_log(tmp_path, "review-pr_2026-06-24_00-00-00.log", age_days=30)

    logging_setup._prune_old_logs(keep=active)

    assert not old.exists()  # older than retention -> removed
    assert recent.exists()  # within retention -> kept
    assert active.exists()  # active file -> always kept, even if old
