#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AUDIT #5 regression tests: broad-except narrowing in l4_fts5_search.

The storage/telemetry methods of L4FTS5Search were narrowed from blanket
``except Exception`` blocks to the realistic failure modes (sqlite3.Error for
DB ops, OSError/UnicodeDecodeError for file reads, and
(sqlite3.Error, OSError, ValueError) for best-effort cost-tracking telemetry).
Each test pins BOTH directions: an expected error degrades gracefully, while
an unexpected (non-narrowed) error propagates so real bugs stay visible.

The hybrid fan-out wrappers (fetch_fts/fetch_semantic/fetch_bm25) are
deliberately NOT covered here -- their broad catch is an intentional per-engine
fault-isolation boundary, already locked by
test_l4_fts5_search.py::test_cmd_hybrid_parallel_engine_failure_degrades_to_remaining_streams.

All tests run against a tmp_path DB with cost tracking disabled, so no network
or ~/.claude access is required.
"""
import importlib
import logging
import sqlite3
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


@pytest.fixture(name="module")
def fixture_module():
    return importlib.import_module("l4_fts5_search")


def _raise_sqlite():
    raise sqlite3.OperationalError("forced sqlite failure")


def _raise_runtime():
    raise RuntimeError("unexpected non-sqlite failure")


# --- init_fts --------------------------------------------------------------


def test_init_fts_degrades_on_sqlite_error(module, tmp_path, monkeypatch, caplog):
    engine = module.L4FTS5Search(db_path=tmp_path / "fts.db")
    monkeypatch.setattr(engine, "_get_connection", _raise_sqlite)
    with caplog.at_level(logging.ERROR):
        assert engine.init_fts() is False
    assert any(
        "FTS5 initialization failed" in r.getMessage() for r in caplog.records
    )


def test_init_fts_propagates_unexpected_error(module, tmp_path, monkeypatch):
    engine = module.L4FTS5Search(db_path=tmp_path / "fts.db")
    monkeypatch.setattr(engine, "_get_connection", _raise_runtime)
    with pytest.raises(RuntimeError, match="unexpected non-sqlite failure"):
        engine.init_fts()


# --- reindex_all -----------------------------------------------------------


def test_reindex_all_degrades_on_sqlite_error(module, tmp_path, monkeypatch):
    engine = module.L4FTS5Search(db_path=tmp_path / "fts.db")
    monkeypatch.setattr(engine, "_get_connection", _raise_sqlite)
    assert engine.reindex_all() == 0


def test_reindex_all_propagates_unexpected_error(module, tmp_path, monkeypatch):
    engine = module.L4FTS5Search(db_path=tmp_path / "fts.db")
    monkeypatch.setattr(engine, "_get_connection", _raise_runtime)
    with pytest.raises(RuntimeError, match="unexpected non-sqlite failure"):
        engine.reindex_all()


def test_reindex_all_one_failing_future_does_not_abort_batch(
    module, tmp_path, monkeypatch, caplog
):
    """Bug #3: a single failing worker future must not abort the whole batch.

    Before the fix, an unexpected error raised by a worker (e.g. from
    ``chunk_text`` or a pool cancellation) bubbled out of
    ``future.result()``, silently aborting reindex and returning 0 files
    with no per-file diagnosis. The fix makes each ``future.result()`` a
    per-task fault-isolation boundary: the failing file is logged and
    skipped, the rest of the batch still completes.
    """
    engine = module.L4FTS5Search(db_path=tmp_path / "fts.db")
    assert engine.init_fts() is True

    # Two files under the (monkeypatched) global memory root.
    memory_root = tmp_path / "memory"
    memory_root.mkdir()
    good = memory_root / "good.md"
    bad = memory_root / "bad.md"
    good.write_text("healthy indexed content", encoding="utf-8")
    bad.write_text("this file will raise while indexing", encoding="utf-8")
    monkeypatch.setattr(engine, "global_memory", memory_root)
    monkeypatch.setattr(engine, "projects_base", tmp_path / "projects")

    real_index = engine._index_single_file

    def flaky_index(md_file, base_path, source):
        if md_file == bad:
            raise RuntimeError("unexpected chunk_text failure")
        return real_index(md_file, base_path, source)

    monkeypatch.setattr(engine, "_index_single_file", flaky_index)

    with caplog.at_level(logging.ERROR):
        # Only the good file is counted; the bad one is skipped, not fatal.
        assert engine.reindex_all() == 1
    assert any(
        "Reindex worker failed" in r.getMessage() and "bad.md" in r.getMessage()
        for r in caplog.records
    )


# --- stats -----------------------------------------------------------------


def test_stats_degrades_on_sqlite_error(module, tmp_path, monkeypatch):
    engine = module.L4FTS5Search(db_path=tmp_path / "fts.db")
    monkeypatch.setattr(engine, "_get_connection", _raise_sqlite)
    stats = engine.stats()
    assert stats == {
        "total_documents": 0,
        "sources": {},
        "db_path": str(engine.db_path),
        "db_size_kb": 0,
    }


def test_stats_propagates_unexpected_error(module, tmp_path, monkeypatch):
    engine = module.L4FTS5Search(db_path=tmp_path / "fts.db")
    monkeypatch.setattr(engine, "_get_connection", _raise_runtime)
    with pytest.raises(RuntimeError, match="unexpected non-sqlite failure"):
        engine.stats()


# --- index_file ------------------------------------------------------------


def test_index_file_degrades_on_sqlite_error(module, tmp_path, monkeypatch):
    engine = module.L4FTS5Search(db_path=tmp_path / "fts.db")
    doc = tmp_path / "notes.md"
    doc.write_text("indexed content", encoding="utf-8")
    monkeypatch.setattr(engine, "_get_connection", _raise_sqlite)
    assert engine.index_file(doc, source="global") is False


def test_index_file_degrades_on_os_error_reading_path(module, tmp_path):
    engine = module.L4FTS5Search(db_path=tmp_path / "fts.db")
    assert engine.init_fts() is True
    a_dir = tmp_path / "a_directory"
    a_dir.mkdir()
    # read_text() on a directory raises an OSError subclass
    # (IsADirectoryError / PermissionError), which the narrowed except must
    # swallow -> False, using a real (initialized) DB connection.
    assert engine.index_file(a_dir, source="global") is False


def test_index_file_propagates_unexpected_error(module, tmp_path, monkeypatch):
    engine = module.L4FTS5Search(db_path=tmp_path / "fts.db")
    doc = tmp_path / "notes.md"
    doc.write_text("indexed content", encoding="utf-8")
    monkeypatch.setattr(engine, "_get_connection", _raise_runtime)
    with pytest.raises(RuntimeError, match="unexpected non-sqlite failure"):
        engine.index_file(doc, source="global")


# --- search() cost-tracking telemetry --------------------------------------


def _build_indexed_engine(module, tmp_path, monkeypatch, content):
    monkeypatch.setattr(module, "COST_TRACKING_ENABLED", False)
    engine = module.L4FTS5Search(db_path=tmp_path / "fts.db")
    assert engine.init_fts() is True
    doc = tmp_path / "notes.md"
    doc.write_text(content, encoding="utf-8")
    assert engine.index_file(doc, source="global") is True
    return engine


def test_search_cost_tracking_expected_error_does_not_break_search(
    module, tmp_path, monkeypatch
):
    engine = _build_indexed_engine(
        module, tmp_path, monkeypatch, "Learning C++ today."
    )
    monkeypatch.setattr(module, "COST_TRACKING_ENABLED", True)

    class _BoomTracker:  # pylint: disable=too-few-public-methods
        def __init__(self):
            raise sqlite3.OperationalError("cost db locked")

    monkeypatch.setattr(module, "CostTracker", _BoomTracker)
    results = engine.search("C++", limit=10)
    # Telemetry failure is swallowed; the search result is still returned.
    assert len(results) >= 1


def test_search_cost_tracking_unexpected_error_propagates(
    module, tmp_path, monkeypatch
):
    engine = _build_indexed_engine(
        module, tmp_path, monkeypatch, "Learning C++ today."
    )
    monkeypatch.setattr(module, "COST_TRACKING_ENABLED", True)

    class _BoomTracker:  # pylint: disable=too-few-public-methods
        def __init__(self):
            raise RuntimeError("unexpected telemetry bug")

    monkeypatch.setattr(module, "CostTracker", _BoomTracker)
    with pytest.raises(RuntimeError, match="unexpected telemetry bug"):
        engine.search("C++", limit=10)
