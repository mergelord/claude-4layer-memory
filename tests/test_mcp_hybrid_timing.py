#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for optional debug timing metadata in hybrid_search_memory."""

import sys
from pathlib import Path
from unittest.mock import patch

ROOT_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = ROOT_DIR / "scripts"
for _entry in (ROOT_DIR, SCRIPTS_DIR):
    if str(_entry) not in sys.path:
        sys.path.insert(0, str(_entry))

import mcp_server  # noqa: E402
from ranking import make_join_key  # noqa: E402


class _FakeEntry:
    def __init__(self, key, score, normalized_score, sources):
        self.key = key
        self.score = score
        self.normalized_score = normalized_score
        self.sources = sources


def test_hybrid_search_debug_includes_timing_meta():
    key = make_join_key("global", "notes.md")
    entry = _FakeEntry(
        key=key,
        score=1.0,
        normalized_score=1.0,
        sources={"fts": [{"snippet": "hello world"}]},
    )
    fake_timing = {
        "fetch_ms": 1.5,
        "merge_ms": 0.2,
        "rerank_ms": 0.0,
        "total_ms": 1.7,
        "cold_start": True,
        "reranked": False,
    }
    with patch.object(
        mcp_server,
        "hybrid_search_timed",
        return_value=([entry], fake_timing),
    ) as mock_timed:
        result = mcp_server.hybrid_search_memory(
            "hello", limit=5, rerank=False, debug=True
        )

    mock_timed.assert_called_once_with(
        mcp_server.fts5_search, "hello", enable_rerank=False
    )
    assert result["success"] is True
    assert result["count"] == 1
    assert "meta" in result
    assert result["meta"]["engine"] == "hybrid"
    assert result["meta"]["timing_ms"] == fake_timing
    assert result["meta"]["total_candidates"] == 1


def test_hybrid_search_default_has_no_meta():
    with patch.object(
        mcp_server, "hybrid_search", return_value=[]
    ) as mock_plain:
        result = mcp_server.hybrid_search_memory("nothing")

    mock_plain.assert_called_once_with(
        mcp_server.fts5_search, "nothing", enable_rerank=True
    )
    assert result == {
        "success": True,
        "query": "nothing",
        "count": 0,
        "results": [],
    }
