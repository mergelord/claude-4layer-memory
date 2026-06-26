"""End-to-end smoke test: every read-only MCP tool returns a success dict.

These call the real tool functions (no mocks) against whatever local state the
CI runner has. They never touch the network (smart_complete and the semantic
backend are intentionally excluded) and never mutate the index (reindex_memory
is called WITHOUT confirmation, so it is a guaranteed no-op). The contract under
test is intentionally loose: each tool must return a ``dict`` whose ``success``
field is a real ``bool`` -- success or a cleanly-handled failure both pass, a
crash or malformed payload does not.
"""
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import mcp_server  # noqa: E402  pylint: disable=wrong-import-position


def _assert_tool_result(result):
    assert isinstance(result, dict)
    assert isinstance(result["success"], bool)


def test_get_memory_stats_smoke():
    _assert_tool_result(mcp_server.get_memory_stats())


def test_search_memory_smoke():
    _assert_tool_result(mcp_server.search_memory("selftest", limit=1))


def test_health_check_smoke():
    _assert_tool_result(mcp_server.health_check(include_semantic=False))


def test_cost_tools_smoke():
    _assert_tool_result(mcp_server.get_cost_stats(days=1))
    _assert_tool_result(mcp_server.get_recent_cost_operations(limit=1))
    _assert_tool_result(mcp_server.get_cost_breakdown(days=1))


def test_reindex_unconfirmed_is_safe_noop():
    """Unconfirmed reindex must report it needs confirmation and not rebuild."""
    result = mcp_server.reindex_memory()
    _assert_tool_result(result)
    assert result["success"] is False
    assert result["requires_confirmation"] is True
