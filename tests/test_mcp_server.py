"""
Smoke tests for mcp_server tool functions.

Verifies that the @mcp.tool() functions return the expected structure
without requiring the MCP runtime to be active.
"""
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

# Add scripts/ to sys.path so mcp_server can resolve l4_fts5_search / cost_tracker
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import mcp_server  # noqa: E402  pylint: disable=wrong-import-position
from l4_fts5_search import SearchResult  # noqa: E402  pylint: disable=wrong-import-position
from ranking import make_join_key  # noqa: E402  pylint: disable=wrong-import-position
from claude_client import approx_tokens  # noqa: E402  pylint: disable=wrong-import-position


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
            key=make_join_key("global", "handoff.md"),
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
            key=make_join_key("global", "handoff.md"),
            snippet="hit",
            rank=0.9,
            source="global",
        ),
        SearchResult(
            path="[global] decisions.md",
            key=make_join_key("global", "decisions.md"),
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


# ---------------------------------------------------------------------------
# smart_complete: cost & success-signal correctness (regression tests)
#
# Before the fix, smart_complete always priced the call as Haiku
# (0.25/1.25 per 1M tokens) regardless of the model the router chose, and
# hardcoded was_successful=True. These tests pin the correct behavior:
# the recorded cost must reflect the chosen model's real price, and the
# success flag must be derived from the response content.
# ---------------------------------------------------------------------------


def _fake_message(text, *, input_tokens=1000, output_tokens=500,
                  cache_creation=0, cache_read=0):
    """Build a lightweight stand-in for an Anthropic message response."""
    return SimpleNamespace(
        content=[SimpleNamespace(text=text)],
        usage=SimpleNamespace(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_creation_input_tokens=cache_creation,
            cache_read_input_tokens=cache_read,
        ),
    )


def _capture_recorded_outcome():
    """Patch predict_model + complete and capture what record_outcome receives."""
    captured = {}

    def fake_record_outcome(**kwargs):
        captured.update(kwargs)
        return "task_id"

    return captured, fake_record_outcome


def test_smart_complete_prices_opus_at_real_rate_not_haiku():
    """Opus (15.0/75.0) must NOT be costed at Haiku's 0.25/1.25."""
    captured, fake_record = _capture_recorded_outcome()

    with patch.object(mcp_server.routing_learner, "predict_model",
                      return_value="claude-opus-4"), \
         patch.object(mcp_server.tracked_claude, "complete",
                      return_value=_fake_message("result body")), \
         patch.object(mcp_server.routing_learner, "record_outcome",
                      side_effect=fake_record):
        mcp_server.smart_complete(task="do something", context="ctx")

    # Real Opus price: 1000 input * 15.0/M + 500 output * 75.0/M = 0.015 + 0.0375
    assert captured["cost_usd"] == pytest.approx(0.015 + 0.0375)
    assert captured["model_used"] == "claude-opus-4"


def test_smart_complete_prices_sonnet_at_real_rate_not_haiku():
    """Sonnet (3.0/15.0) must NOT be costed at Haiku's 0.25/1.25."""
    captured, fake_record = _capture_recorded_outcome()

    with patch.object(mcp_server.routing_learner, "predict_model",
                      return_value="claude-sonnet-4"), \
         patch.object(mcp_server.tracked_claude, "complete",
                      return_value=_fake_message("ok")), \
         patch.object(mcp_server.routing_learner, "record_outcome",
                      side_effect=fake_record):
        mcp_server.smart_complete(task="t")

    # 1000 * 3.0/M + 500 * 15.0/M = 0.003 + 0.0075
    assert captured["cost_usd"] == pytest.approx(0.003 + 0.0075)
    assert captured["model_used"] == "claude-sonnet-4"


def test_smart_complete_prices_haiku_at_haiku_rate():
    """Haiku keeps its own (low) price — no regression for the cheap model."""
    captured, fake_record = _capture_recorded_outcome()

    with patch.object(mcp_server.routing_learner, "predict_model",
                      return_value="claude-haiku-4"), \
         patch.object(mcp_server.tracked_claude, "complete",
                      return_value=_fake_message("ok")), \
         patch.object(mcp_server.routing_learner, "record_outcome",
                      side_effect=fake_record):
        mcp_server.smart_complete(task="t")

    assert captured["cost_usd"] == pytest.approx(0.00025 + 0.000625)


def test_smart_complete_cost_includes_cache_tiers():
    """Cost must account for cache_creation and cache_read tokens, not just I/O."""
    captured, fake_record = _capture_recorded_outcome()

    with patch.object(mcp_server.routing_learner, "predict_model",
                      return_value="claude-sonnet-4"), \
         patch.object(mcp_server.tracked_claude, "complete",
                      return_value=_fake_message(
                          "ok", input_tokens=0, output_tokens=0,
                          cache_creation=1_000_000, cache_read=1_000_000,
                      )), \
         patch.object(mcp_server.routing_learner, "record_outcome",
                      side_effect=fake_record):
        mcp_server.smart_complete(task="t")

    # Sonnet: cache_creation 3.75/M * 1M = 3.75 ; cache_read 0.30/M * 1M = 0.30
    assert captured["cost_usd"] == pytest.approx(3.75 + 0.30)


def test_smart_complete_marks_empty_response_as_failed():
    """Empty/whitespace reply → was_successful=False (learner gets a real signal)."""
    captured, fake_record = _capture_recorded_outcome()

    with patch.object(mcp_server.routing_learner, "predict_model",
                      return_value="claude-sonnet-4"), \
         patch.object(mcp_server.tracked_claude, "complete",
                      return_value=_fake_message("   \n  ")), \
         patch.object(mcp_server.routing_learner, "record_outcome",
                      side_effect=fake_record):
        mcp_server.smart_complete(task="t")

    assert captured["was_successful"] is False


def test_smart_complete_marks_nonempty_response_as_successful():
    """A real answer → was_successful=True (sanity check, was the old behavior)."""
    captured, fake_record = _capture_recorded_outcome()

    with patch.object(mcp_server.routing_learner, "predict_model",
                      return_value="claude-sonnet-4"), \
         patch.object(mcp_server.tracked_claude, "complete",
                      return_value=_fake_message("def f(): pass")), \
         patch.object(mcp_server.routing_learner, "record_outcome",
                      side_effect=fake_record):
        mcp_server.smart_complete(task="t")

    assert captured["was_successful"] is True


def test_smart_complete_passes_real_token_counts_to_record_outcome():
    """record_outcome must receive the actual usage from the API, not zeros."""
    captured, fake_record = _capture_recorded_outcome()

    with patch.object(mcp_server.routing_learner, "predict_model",
                      return_value="claude-haiku-4"), \
         patch.object(mcp_server.tracked_claude, "complete",
                      return_value=_fake_message(
                          "ok", input_tokens=4321, output_tokens=1234,
                      )), \
         patch.object(mcp_server.routing_learner, "record_outcome",
                      side_effect=fake_record):
        mcp_server.smart_complete(task="t")

    assert captured["tokens"] == {"input": 4321, "output": 1234}


def test_smart_complete_still_returns_response_to_caller():
    """The fix must not change the tool's external contract."""
    msg = _fake_message("hello world", input_tokens=10, output_tokens=5)
    with patch.object(mcp_server.routing_learner, "predict_model",
                      return_value="claude-haiku-4"), \
         patch.object(mcp_server.tracked_claude, "complete", return_value=msg), \
         patch.object(mcp_server.routing_learner, "record_outcome"):
        result = mcp_server.smart_complete(task="t", context="c")

    assert result["success"] is True
    assert result["result"] == "hello world"
    assert result["usage"]["input_tokens"] == 10
    assert result["usage"]["output_tokens"] == 5


# ---------------------------------------------------------------------------
# smart_complete: routing bridge -- context_len must be TOKEN-based, not words
#
# Regression net for commit 208fa77 ("context_len counts tokens, not words").
# mcp_server previously passed len(context.split()) (a *word* count) to the
# router, which compares against token thresholds (8000/30000/80000) and so
# under-estimated complexity for code- and Cyrillic-heavy context.
# smart_complete now feeds approx_tokens(context); these tests pin that bridge
# so it cannot silently regress back to word counting.
# ---------------------------------------------------------------------------


def _capture_predicted_context_len():
    """Patch predict_model and capture the context_len it was called with."""
    captured = {}

    def fake_predict(*_args, **kwargs):
        captured["context_len"] = kwargs["context_len"]
        return "claude-haiku-4"

    return captured, fake_predict


def test_smart_complete_passes_token_based_context_len_to_router():
    """predict_model must receive context_len == approx_tokens(context)."""
    captured, fake_predict = _capture_predicted_context_len()
    context = "def add(a, b):\n    return a + b\n" * 50

    with patch.object(mcp_server.routing_learner, "predict_model",
                      side_effect=fake_predict), \
         patch.object(mcp_server.tracked_claude, "complete",
                      return_value=_fake_message("ok")), \
         patch.object(mcp_server.routing_learner, "record_outcome"):
        mcp_server.smart_complete(task="t", context=context)

    assert captured["context_len"] == approx_tokens(context)
    # Token estimate must exceed the raw word count (the 1.3x factor),
    # proving the value is token-based, not the old len(context.split()).
    assert captured["context_len"] > len(context.split())


def test_smart_complete_passes_zero_context_len_when_no_context():
    """No context -> context_len is exactly 0 (no spurious token estimate)."""
    captured, fake_predict = _capture_predicted_context_len()

    with patch.object(mcp_server.routing_learner, "predict_model",
                      side_effect=fake_predict), \
         patch.object(mcp_server.tracked_claude, "complete",
                      return_value=_fake_message("ok")), \
         patch.object(mcp_server.routing_learner, "record_outcome"):
        mcp_server.smart_complete(task="t")

    assert captured["context_len"] == 0
