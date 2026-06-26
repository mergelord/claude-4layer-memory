#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for incremental FTS5 reindexing (mtime/size based)."""

import os
import sys
import time
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import l4_fts5_search  # noqa: E402
from l4_fts5_search import L4FTS5Search  # noqa: E402


def _make_engine(tmp_path, monkeypatch):
    home = tmp_path / "home"
    (home / "memory").mkdir(parents=True)
    monkeypatch.setenv("L4_HOME", str(home))
    monkeypatch.setattr(l4_fts5_search, "COST_TRACKING_ENABLED", False)
    engine = L4FTS5Search(db_path=tmp_path / "fts.db")
    engine.init_fts()
    return engine, home


def test_incremental_adds_then_reports_unchanged(tmp_path, monkeypatch):
    engine, home = _make_engine(tmp_path, monkeypatch)
    note = home / "memory" / "notes.md"
    note.write_text("# Title\n\nalpha beta gamma", encoding="utf-8")

    first = engine.reindex_incremental()
    assert first["added"] == 1
    assert first["updated"] == 0
    assert first["indexed"] == 1

    second = engine.reindex_incremental()
    assert second["added"] == 0
    assert second["updated"] == 0
    assert second["unchanged"] == 1
    assert second["indexed"] == 0


def test_incremental_detects_modification(tmp_path, monkeypatch):
    engine, home = _make_engine(tmp_path, monkeypatch)
    note = home / "memory" / "notes.md"
    note.write_text("original content here", encoding="utf-8")
    engine.reindex_incremental()

    note.write_text("totally different updated content", encoding="utf-8")
    future = time.time() + 10
    os.utime(note, (future, future))

    result = engine.reindex_incremental()
    assert result["updated"] == 1
    assert result["added"] == 0
    assert result["indexed"] == 1


def test_incremental_removes_deleted_file(tmp_path, monkeypatch):
    engine, home = _make_engine(tmp_path, monkeypatch)
    note = home / "memory" / "notes.md"
    note.write_text("some indexed words", encoding="utf-8")
    engine.reindex_incremental()
    assert engine.stats()["total_documents"] > 0

    note.unlink()
    result = engine.reindex_incremental()
    assert result["removed"] == 1
    assert engine.stats()["total_documents"] == 0


def test_reindex_all_then_incremental_is_unchanged(tmp_path, monkeypatch):
    engine, home = _make_engine(tmp_path, monkeypatch)
    note = home / "memory" / "notes.md"
    note.write_text("content for full rebuild", encoding="utf-8")

    assert engine.reindex_all() == 1

    result = engine.reindex_incremental()
    assert result["unchanged"] == 1
    assert result["added"] == 0
    assert result["updated"] == 0
