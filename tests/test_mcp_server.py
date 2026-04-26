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
