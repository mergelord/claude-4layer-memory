#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the MCP hybrid_search_memory tool wrapper."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import mcp_server  # noqa: E402  pylint: disable=wrong-import-position
from ranking import make_join_key  # noqa: E402  pylint: disable=wrong-import-position


class _FakeEntry:  # pylint: disable=too-few-public-methods
    """Minimal stand-in for ranking.RankedResult."""

    def __init__(self, key, score, normalized_score, sources):
        self.key = key
        self.score = score
        self.normalized_score = normalized_score
        self.sources = sources


def test_hybrid_search_memory_wraps_merged_results():
    """hybrid_search_memory must wrap RankedResult entries into dicts."""
    fake_merged = [
        _FakeEntry(
            key=make_join_key("global", "notes.md"),
            score=0.123,
            normalized_score=1.0,
            sources={
                # Unsorted on purpose: wrapper must sort source names and then
                # pick the first non-empty snippet/text across sorted sources.
                "semantic": [{"text": "semantic text"}],
                "fts": [{"snippet": "fts snippet"}],
            },
        )
    ]

    with patch.object(mcp_server, "hybrid_search", return_value=fake_merged) as mock:
        result = mcp_server.hybrid_search_memory("hello", limit=5, rerank=False)

    mock.assert_called_once_with(mcp_server.fts5_search, "hello", enable_rerank=False)
    assert result["success"] is True
    assert result["query"] == "hello"
    assert result["count"] == 1
    entry = result["results"][0]
    assert entry["key"] == make_join_key("global", "notes.md")
    assert entry["score"] == 0.123
    assert entry["normalized_score"] == 1.0
    assert entry["sources"] == ["fts", "semantic"]
    assert entry["snippet"] == "fts snippet"


def test_hybrid_search_memory_empty_results_are_successful():
    """An empty hybrid ranking is a successful empty result, not an error."""
    with patch.object(mcp_server, "hybrid_search", return_value=[]):
        result = mcp_server.hybrid_search_memory("nothing")

    assert result == {
        "success": True,
        "query": "nothing",
        "count": 0,
        "results": [],
    }


def test_hybrid_search_memory_handles_failure():
    """hybrid_search_memory must degrade to success=False on API exceptions."""
    with patch.object(
        mcp_server, "hybrid_search", side_effect=RuntimeError("boom")
    ):
        result = mcp_server.hybrid_search_memory("hello")

    assert result["success"] is False
    assert "boom" in result["error"]
