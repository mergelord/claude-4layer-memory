#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Regression tests for AUDIT #6 — SQLite write-concurrency hardening in
``cost_tracker.CostTracker._get_connection``.

Covers:
- WAL journaling and ``busy_timeout`` are actually applied to connections.
- ``_commit_with_retry`` recovers from a transient "database is locked".
- ``_commit_with_retry`` propagates a non-lock error immediately (no retry).
- ``_commit_with_retry`` gives up (re-raises) after exhausting retries.
- The context manager still rolls back and re-raises on an in-body error.
- Concurrent writers from multiple threads all succeed without lost writes.
"""

import sqlite3
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts import cost_tracker
from scripts.cost_tracker import CostTracker


class _FlakyConn:
    """Minimal connection double whose ``commit`` fails a fixed number of
    times before succeeding. Used to exercise ``_commit_with_retry`` in
    isolation, without a real database."""

    def __init__(self, fail_times: int, exc: Exception):
        self._fail_times = fail_times
        self._exc = exc
        self.commit_calls = 0

    def commit(self):
        self.commit_calls += 1
        if self.commit_calls <= self._fail_times:
            raise self._exc


def test_commit_with_retry_recovers_from_transient_lock(monkeypatch):
    """Two "database is locked" failures are retried, then commit succeeds.
    Sleeps happen only between attempts."""
    sleeps = []
    monkeypatch.setattr(cost_tracker.time, "sleep", lambda s: sleeps.append(s))

    conn = _FlakyConn(2, sqlite3.OperationalError("database is locked"))
    CostTracker._commit_with_retry(conn, retries=3, delay=0.01)

    assert conn.commit_calls == 3
    assert sleeps == [0.01, 0.01]


def test_commit_with_retry_propagates_non_lock_error(monkeypatch):
    """A non-lock OperationalError is a real failure: propagate on the first
    attempt with no retry and no sleep."""
    slept = []
    monkeypatch.setattr(cost_tracker.time, "sleep", lambda s: slept.append(s))

    conn = _FlakyConn(1, sqlite3.OperationalError("no such table: operations"))
    with pytest.raises(sqlite3.OperationalError, match="no such table"):
        CostTracker._commit_with_retry(conn, retries=3, delay=0.01)

    assert conn.commit_calls == 1
    assert slept == []


def test_commit_with_retry_gives_up_after_retries(monkeypatch):
    """A persistent lock is retried up to ``retries`` times, then re-raised."""
    sleeps = []
    monkeypatch.setattr(cost_tracker.time, "sleep", lambda s: sleeps.append(s))

    conn = _FlakyConn(99, sqlite3.OperationalError("database is locked"))
    with pytest.raises(sqlite3.OperationalError, match="locked"):
        CostTracker._commit_with_retry(conn, retries=3, delay=0.01)

    assert conn.commit_calls == 3
    assert sleeps == [0.01, 0.01]


def test_get_connection_enables_wal_and_busy_timeout(tmp_path):
    """The connection context manager applies the AUDIT #6 PRAGMAs."""
    tracker = CostTracker(tmp_path / "wal.db")
    with tracker._get_connection() as conn:
        journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        busy_timeout = conn.execute("PRAGMA busy_timeout").fetchone()[0]

    assert str(journal_mode).lower() == "wal"
    assert busy_timeout == 30000


def test_get_connection_rolls_back_on_error(tmp_path):
    """An error inside the ``with`` block rolls back the pending write and
    re-raises — commit semantics are preserved alongside the new PRAGMAs."""
    tracker = CostTracker(tmp_path / "rollback.db")

    with pytest.raises(sqlite3.OperationalError):
        with tracker._get_connection() as conn:
            conn.execute(
                "INSERT INTO operations (timestamp, operation_type) "
                "VALUES (?, ?)",
                ("2026-01-01T00:00:00+00:00", "should_roll_back"),
            )
            # Force a failure *after* a successful write.
            conn.execute("SELECT * FROM definitely_not_a_table")

    # The insert must not have persisted.
    stats = tracker.get_stats(days=3650)
    assert stats["total_operations"] == 0


def test_concurrent_writers_all_persist(tmp_path):
    """Multiple threads writing to the same DB under WAL + busy_timeout all
    succeed; every operation is persisted (no lost writes, no exceptions)."""
    db_path = tmp_path / "concurrent.db"
    # Initialise the schema once up front.
    CostTracker(db_path)

    writers = 4
    ops_per_writer = 5

    def worker(worker_id: int) -> int:
        tracker = CostTracker(db_path)
        for _ in range(ops_per_writer):
            tracker.track_operation(f"op{worker_id}", input_tokens=10)
        return worker_id

    with ThreadPoolExecutor(max_workers=writers) as executor:
        futures = [executor.submit(worker, n) for n in range(writers)]
        # ``result()`` re-raises any exception raised inside a worker thread.
        for future in futures:
            future.result()

    stats = CostTracker(db_path).get_stats(days=3650)
    assert stats["total_operations"] == writers * ops_per_writer


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
