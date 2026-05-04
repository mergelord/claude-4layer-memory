"""
Smoke tests for mcp_server tool functions.

Verifies that the @mcp.tool() functions return the expected structure
without requiring the MCP runtime to be active.
"""
import sys
from pathlib import Path
from unittest.mock import patch

# Add scripts/ to sys.path so mcp_server can resolve l4_fts5_search / cost_tracker
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import mcp_server  # noqa: E402  pylint: disable=wrong-import-position
from l4_fts5_search import SearchResult  # noqa: E402  pylint: disable=wrong-import-position


def test_reindex_memory_returns_dict_with_int_count():
    """reindex_memory must call reindex_all() (not reindex()) and return int count."""
    with patch.object(mcp_server.fts5_search, "reindex_all", return_value=42) as mock:
        result = mcp_server.reindex_memory()

    mock.assert_called_once()
    assert result == {"success": True, "indexed_files": 42}


def test_reindex_memory_handles_failure():
    """reindex_memory must return success=False with error string on exception."""
    with patch.object(
        mcp_server.fts5_search, "reindex_all", side_effect=RuntimeError("boom")
    ):
        result = mcp_server.reindex_memory()

    assert result["success"] is False
    assert "boom" in result["error"]


def test_search_memory_returns_results():
    """search_memory must wrap fts5_search.search() results into dict."""
    fake_results = [
        SearchResult(
            path="/x/handoff.md",
            snippet="hello world",
            rank=1.0,
            source="global",
        )
    ]
    with patch.object(mcp_server.fts5_search, "search", return_value=fake_results):
        result = mcp_server.search_memory("hello", limit=5)

    assert result["success"] is True
    assert result["count"] == 1
    assert result["results"][0]["path"] == "/x/handoff.md"


def test_search_memory_omits_meta_when_debug_false():
    """Debug payload is opt-in — must not appear in default responses."""
    with patch.object(mcp_server.fts5_search, "search", return_value=[]):
        result = mcp_server.search_memory("ping", limit=3)

    assert "meta" not in result


def test_search_memory_emits_structured_meta_when_debug_true():
    """debug=True → response['meta'] is a dict with the documented schema."""
    fake_results = [
        SearchResult(
            path="[global] handoff.md",
            snippet="hit",
            rank=0.9,
            source="global",
        ),
        SearchResult(
            path="[global] decisions.md",
            snippet="hit2",
            rank=0.5,
            source="global",
        ),
    ]
    with patch.object(mcp_server.fts5_search, "search", return_value=fake_results):
        result = mcp_server.search_memory("session handoff", limit=5, debug=True)

    assert result["success"] is True
    assert "meta" in result
    meta = result["meta"]
    assert meta["engine"] == "fts5"
    assert meta["query"] == "session handoff"
    assert meta["query_tokens"] == ["session", "handoff"]
    assert meta["limit"] == 5
    assert meta["total_candidates"] == 2


def test_search_memory_meta_total_candidates_zero_for_empty_results():
    """Empty result set must still produce a well-formed meta block."""
    with patch.object(mcp_server.fts5_search, "search", return_value=[]):
        result = mcp_server.search_memory("nothing", limit=10, debug=True)

    assert result["meta"]["total_candidates"] == 0
    assert result["meta"]["query_tokens"] == ["nothing"]
