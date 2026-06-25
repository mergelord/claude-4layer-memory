#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the programmatic hybrid_search() return-value API."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from ranking import make_join_key  # noqa: E402  pylint: disable=wrong-import-position


@pytest.fixture(name="module")
def fixture_module():
    """Provide the hybrid API module under test."""
    return importlib.import_module("l4_hybrid_search")


def _make_search_result(module: Any, source: str, rel_path: str, snippet="snippet") -> Any:
    """Build an l4_fts5_search.SearchResult for fake FTS streams."""
    return module._fts5.SearchResult(  # pylint: disable=protected-access
        path=f"[{source}] {rel_path}",
        key=make_join_key(source, rel_path),
        snippet=snippet,
        rank=-1.0,
        source="fts5",
    )


def test_hybrid_search_returns_merged_ranking(module, monkeypatch):
    """hybrid_search() must return RankedResult entries, not print stdout."""
    fts_mock = MagicMock(spec=module.L4FTS5Search)
    fts_mock.search.return_value = [
        _make_search_result(module, "global", "notes.md", snippet="alpha fts")
    ]
    semantic_results = [
        {"key": "[global] notes.md", "text": "alpha sem", "distance": 0.1, "rank": 0}
    ]

    monkeypatch.setattr(
        module._fts5, "_fetch_semantic_results", lambda query: semantic_results
    )
    monkeypatch.setattr(module._fts5, "fetch_bm25_results", None)
    rerank_lookup = MagicMock(return_value=None)
    monkeypatch.setattr(module._fts5, "_get_l4_rerank", rerank_lookup)

    merged = module.hybrid_search(fts_mock, "alpha", enable_rerank=False)

    assert len(merged) == 1
    entry = merged[0]
    assert entry.key == make_join_key("global", "notes.md")
    assert set(entry.sources.keys()) == {"fts", "semantic"}
    assert entry.normalized_score == 1.0
    assert rerank_lookup.call_count == 0


def test_hybrid_search_returns_empty_when_no_engine_has_hits(module, monkeypatch):
    """No FTS/semantic/BM25 hits -> [] for programmatic callers."""
    fts_mock = MagicMock(spec=module.L4FTS5Search)
    fts_mock.search.return_value = []

    monkeypatch.setattr(module._fts5, "_fetch_semantic_results", lambda query: [])
    monkeypatch.setattr(module._fts5, "fetch_bm25_results", None)

    assert module.hybrid_search(fts_mock, "nothing", enable_rerank=False) == []
