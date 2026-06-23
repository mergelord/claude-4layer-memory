#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MCP Server for Claude 4-Layer Memory System

Provides access to memory through Model Context Protocol:
- FTS5 keyword search
- Semantic search
- Memory statistics
- Cost tracking
"""

import sys
import logging
from typing import Any
from pathlib import Path

from mcp.server.fastmcp import FastMCP

logging.basicConfig(
    level=logging.INFO,
    format='[%(levelname)s] %(message)s',
    stream=sys.stderr,
)

_SCRIPTS_DIR = str(Path(__file__).resolve().parent / "scripts")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from l4_fts5_search import L4FTS5Search  # noqa: E402
from cost_tracker import (  # noqa: E402
    CACHE_CREATION_PRICE_KEY,
    CACHE_READ_PRICE_KEY,
    CostTracker,
)
from claude_client import TrackedClaudeClient  # noqa: E402
from routing_learner import get_learner  # noqa: E402

mcp = FastMCP("claude-4layer-memory")

fts5_search = L4FTS5Search()
cost_tracker = CostTracker()
routing_learner = get_learner()

# Anthropic-backed client, kept at module scope so it can be monkeypatched in
# tests via ``mcp_server.tracked_claude``. Eager construction is safe even
# without ANTHROPIC_API_KEY configured: claude_client builds
# anthropic.Anthropic() with empty kwargs and defers credential validation to
# the first real API call, so importing this module never crashes. Only an
# actual smart_complete call hits the network, and any auth/transport failure
# there is caught below and returned as a clean tool error -- local memory
# search and cost tracking never touch the Anthropic API and are unaffected.
tracked_claude = TrackedClaudeClient(cost_tracker=cost_tracker)


def _extract_text(message: Any) -> str:
    content = getattr(message, "content", None)
    if content is None:
        return ""
    if isinstance(content, list):
        return "\n".join(block.text for block in content if hasattr(block, "text"))
    if hasattr(content, "text"):
        return content.text
    return str(content)


def _extract_usage(message: Any) -> dict[str, int]:
    usage = getattr(message, "usage", None)
    if usage is None:
        return {}
    result: dict[str, int] = {}
    for field in (
        "input_tokens", "output_tokens",
        "cache_creation_input_tokens", "cache_read_input_tokens",
    ):
        val = getattr(usage, field, 0)
        result[field] = int(val or 0)
    return result


# ---------------------------------------------------------------------------
# Memory tools
# ---------------------------------------------------------------------------

@mcp.tool()
def search_memory(query: str, limit: int = 10, debug: bool = False) -> dict[str, Any]:
    """Search memory via FTS5 keyword search."""
    try:
        results = fts5_search.search(query, limit)
        response: dict[str, Any] = {
            "success": True, "query": query, "count": len(results),
            "results": [
                {"path": r.path, "snippet": r.snippet, "rank": r.rank, "source": r.source}
                for r in results
            ],
        }
        if debug:
            response["meta"] = {"engine": "fts5", "query": query, "query_tokens": query.split(), "limit": limit, "total_candidates": len(results)}
        return response
    except Exception as e:
        logging.error("Search failed: %s", e)
        return {"success": False, "error": str(e)}


@mcp.tool()
def get_memory_stats() -> dict[str, Any]:
    """Get FTS5 index statistics."""
    try:
        return {"success": True, "stats": fts5_search.stats()}
    except Exception as e:
        logging.error("Stats failed: %s", e)
        return {"success": False, "error": str(e)}


@mcp.tool()
def reindex_memory() -> dict[str, Any]:
    """Reindex the FTS5 database."""
    try:
        return {"success": True, "indexed_files": fts5_search.reindex_all()}
    except Exception as e:
        logging.error("Reindex failed: %s", e)
        return {"success": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Cost tracking
# ---------------------------------------------------------------------------

@mcp.tool()
def track_claude_usage(
    operation_type: str, model: str,
    input_tokens: int = 0, output_tokens: int = 0,
    cache_creation_input_tokens: int = 0, cache_read_input_tokens: int = 0,
    request_id: str | None = None, metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Record exact Claude token usage."""
    try:
        result = cost_tracker.track_claude_usage(
            operation_type=operation_type, model=model,
            usage={
                "input_tokens": input_tokens, "output_tokens": output_tokens,
                "cache_creation_input_tokens": cache_creation_input_tokens,
                "cache_read_input_tokens": cache_read_input_tokens,
            },
            request_id=request_id, metadata=metadata,
        )
        return {"success": True, "tracked": result}
    except Exception as e:
        logging.error("Track failed: %s", e)
        return {"success": False, "error": str(e)}


@mcp.tool()
def get_cost_stats(days: int = 7) -> dict[str, Any]:
    """Get cost statistics for memory operations."""
    try:
        return {"success": True, "stats": cost_tracker.get_stats(days)}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
def get_cost_stats_by_metadata(key: str = "task", days: int = 7) -> dict[str, Any]:
    """Get cost stats grouped by metadata key."""
    try:
        return {"success": True, "key": key, "period_days": days, "stats": cost_tracker.get_stats_by_metadata_key(key, days)}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
def get_recent_cost_operations(limit: int = 20) -> dict[str, Any]:
    """Get recent cost tracker entries."""
    try:
        ops = cost_tracker.get_recent_operations(limit)
        return {"success": True, "count": len(ops), "operations": ops}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
def get_cost_breakdown(days: int = 7) -> dict[str, Any]:
    """Get spending breakdown by category."""
    try:
        return {"success": True, "period_days": days, "breakdown": cost_tracker.get_model_breakdown(days)}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Code execution tool (stealth routing -- no mention of models)
# ---------------------------------------------------------------------------


def _approx_tokens(text: str) -> int:
    """Estimate token count from text. ~1.3 tokens per word for English,
    more for code/Cyrillic. Simple heuristic: words * 1.3."""
    return int(len(text.split()) * 1.3)


@mcp.tool()
def smart_complete(
    task: str,
    context: str = "",
    max_tokens: int = 4096,
) -> dict[str, Any]:
    """
    Execute a code writing or modification task.

    ALWAYS use this tool instead of writing code yourself when the user
    asks to create, modify, or refactor code.

    Use this for:
    - Writing new functions, modules, or components
    - Modifying existing code
    - Refactoring
    - Fixing bugs
    - Writing tests
    - Any task that produces code as output

    Do NOT use this for:
    - Reading files (use Read tool)
    - Searching code (use Grep/Glob)
    - Simple questions about the project
    - Tasks with only a 1-3 line answer

    Args:
        task: What to do.
        context: Relevant code or project context (paste file contents here).
        max_tokens: Max output length (default: 4096).
    """
    chosen_model: str | None = None
    try:
        prompt = f"Context:\n{context}\n\nTask:\n{task}" if context else task
        context_len = _approx_tokens(context) if context else 0

        # ---- internal: pick the right model (stealth -- NEVER mention to Claude) ----
        chosen_model = routing_learner.predict_model(
            task, context_len=context_len, operation_type="smart_complete",
        )

        message = tracked_claude.complete(
            prompt=prompt,
            model=chosen_model,
            max_tokens=max_tokens,
            operation_type="smart_complete",
            cost_metadata={"task": task[:120]},
        )

        usage = _extract_usage(message)
        result_text = _extract_text(message)

        # Internal learning -- never surfaced to Claude.
        #
        # Cost is computed from the SAME per-model price table the
        # CostTracker uses (cost_tracker.resolve_price), so Opus and
        # Sonnet are no longer mis-priced as Haiku. Includes cache tiers
        # (cache_creation / cache_read) so the recorded cost matches the
        # authoritative ledger entry persisted by tracked_claude.complete.
        prices = cost_tracker.resolve_price(chosen_model)
        input_tokens = usage.get("input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)
        cache_creation = usage.get("cache_creation_input_tokens", 0)
        cache_read = usage.get("cache_read_input_tokens", 0)
        cost_est = (
            input_tokens / 1_000_000 * prices["input"]
            + output_tokens / 1_000_000 * prices["output"]
            + cache_creation / 1_000_000 * prices[CACHE_CREATION_PRICE_KEY]
            + cache_read / 1_000_000 * prices[CACHE_READ_PRICE_KEY]
        )

        # Success is derived from the response, not hard-wired to True:
        # an empty/refusal reply is treated as a failed task so the
        # learner gets a real negative signal to route away from that
        # model for similar tasks.
        was_successful = bool(result_text.strip())

        routing_learner.record_outcome(
            task=task,
            model_used=chosen_model,
            was_successful=was_successful,
            operation_type="smart_complete",
            tokens={"input": input_tokens, "output": output_tokens},
            cost_usd=cost_est,
        )

        return {
            "success": True,
            "result": result_text,
            "usage": usage,
        }

    except Exception as e:
        logging.error("smart_complete failed: %s", e)
        # Record failure so the routing learner avoids models that
        # consistently error out (transport timeouts, auth failures, etc.).
        if chosen_model:
            try:
                routing_learner.record_outcome(
                    task=task,
                    model_used=chosen_model,
                    was_successful=False,
                    operation_type="smart_complete",
                    tokens={"input": 0, "output": 0},
                    cost_usd=0.0,
                )
            except Exception:
                logging.debug("Failed to record routing outcome for error", exc_info=True)
        return {"success": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Resources
# ---------------------------------------------------------------------------

@mcp.resource("memory://global/handoff")
def get_global_handoff() -> str:
    try:
        p = Path.home() / ".claude" / "memory" / "handoff.md"
        return p.read_text(encoding='utf-8') if p.exists() else "# No handoff data"
    except Exception as e:
        return f"# Error: {e}"


@mcp.resource("memory://global/decisions")
def get_global_decisions() -> str:
    try:
        p = Path.home() / ".claude" / "memory" / "decisions.md"
        return p.read_text(encoding='utf-8') if p.exists() else "# No decisions data"
    except Exception as e:
        return f"# Error: {e}"


if __name__ == "__main__":
    mcp.run()
