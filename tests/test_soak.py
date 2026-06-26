"""Lightweight soak test for search_memory.

Drives many sequential search_memory calls with the underlying FTS5 engine
mocked out, asserting the tool stays correct and reasonably fast under repeated
invocation. Bounds are deliberately lenient so this never flakes on slow CI
runners; it is a smoke-level stability check, not a benchmark.
"""
import sys
import time
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import mcp_server  # noqa: E402  pylint: disable=wrong-import-position


def test_search_memory_soak(monkeypatch):
    calls = {"n": 0}

    def fake_search(query, limit):  # noqa: ARG001
        calls["n"] += 1
        return []

    monkeypatch.setattr(mcp_server.fts5_search, "search", fake_search)

    iterations = 300
    start = time.time()
    for _ in range(iterations):
        result = mcp_server.search_memory("ping", limit=5)
        assert result["success"] is True
        assert result["count"] == 0
    elapsed = time.time() - start

    assert calls["n"] == iterations
    # Very generous upper bound: 300 mocked calls should finish in well under
    # 30s even on a heavily loaded CI runner.
    assert elapsed < 30.0
