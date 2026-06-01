#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MCP Server for Claude 4-Layer Memory System

Provides access to memory through Model Context Protocol:
- FTS5 keyword search
- Semantic search
- Memory statistics
- Cost tracking
- Model routing (automatic escalation Haiku → Sonnet → Opus)
"""

import sys
import logging
from typing import Any
from pathlib import Path

from mcp.server.fastmcp import FastMCP

# Logging to stderr (MCP requirement)
logging.basicConfig(
    level=logging.INFO,
    format='[%(levelname)s] %(message)s',
    stream=sys.stderr,
)

# Import our modules — scripts are one directory below the repo root
_SCRIPTS_DIR = str(Path(__file__).resolve().parent / "scripts")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from l4_fts5_search import L4FTS5Search  # noqa: E402
from cost_tracker import CostTracker  # noqa: E402
from claude_client import TrackedClaudeClient  # noqa: E402

# Initialise MCP server
mcp = FastMCP("claude-4layer-memory")

# Initialise components
fts5_search = L4FTS5Search()
cost_tracker = CostTracker()
tracked_claude = TrackedClaudeClient(cost_tracker=cost_tracker)


# ---------------------------------------------------------------------------
# FTS5 memory search
# ---------------------------------------------------------------------------

@mcp.tool()
def search_memory(
    query: str,
    limit: int = 10,
    debug: bool = False,
) -> dict[str, Any]:
    """
    Search memory via FTS5 keyword search.

    Args:
        query: Search query.
        limit: Max results (default: 10).
        debug: If True, response includes a ``meta`` block with structured
            explanation (query tokens, candidate count, engine identification).

    Returns:
        ``{"success": True, "query": str, "count": int, "results": [...]}``.
        When ``debug=True``, ``"meta": {...}`` is added.
    """
    try:
        results = fts5_search.search(query, limit)

        response: dict[str, Any] = {
            "success": True,
            "query": query,
            "count": len(results),
            "results": [
                {
                    "path": r.path,
                    "snippet": r.snippet,
                    "rank": r.rank,
                    "source": r.source,
                }
                for r in results
            ],
        }

        if debug:
            response["meta"] = {
                "engine": "fts5",
                "query": query,
                "query_tokens": query.split(),
                "limit": limit,
                "total_candidates": len(results),
            }

        return response
    except Exception as e:
        logging.error("Search failed: %s", e)
        return {"success": False, "error": str(e)}


@mcp.tool()
def get_memory_stats() -> dict[str, Any]:
    """
    Get FTS5 index statistics.

    Returns:
        Statistics: document count, DB size, sources.
    """
    try:
        stats = fts5_search.stats()
        return {"success": True, "stats": stats}
    except Exception as e:
        logging.error("Stats failed: %s", e)
        return {"success": False, "error": str(e)}


@mcp.tool()
def reindex_memory() -> dict[str, Any]:
    """
    Reindex the FTS5 database.

    Returns:
        Reindex result with indexed file count.
    """
    try:
        indexed_count = fts5_search.reindex_all()
        return {"success": True, "indexed_files": indexed_count}
    except Exception as e:
        logging.error("Reindex failed: %s", e)
        return {"success": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Cost tracking (exact Claude usage from API)
# ---------------------------------------------------------------------------

@mcp.tool()
def track_claude_usage(
    operation_type: str,
    model: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_creation_input_tokens: int = 0,
    cache_read_input_tokens: int = 0,
    request_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Record exact Claude token usage from an Anthropic API response.

    Args:
        operation_type: Cost-tracker operation name.
        model: Claude model name from API response.
        input_tokens: usage.input_tokens.
        output_tokens: usage.output_tokens.
        cache_creation_input_tokens: usage.cache_creation_input_tokens.
        cache_read_input_tokens: usage.cache_read_input_tokens.
        request_id: Claude message/request ID if available.
        metadata: Additional JSON-compatible context.

    Returns:
        Recorded entry with calculated cost.
    """
    try:
        result = cost_tracker.track_claude_usage(
            operation_type=operation_type,
            model=model,
            usage={
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cache_creation_input_tokens": cache_creation_input_tokens,
                "cache_read_input_tokens": cache_read_input_tokens,
            },
            request_id=request_id,
            metadata=metadata,
        )
        return {"success": True, "tracked": result}
    except Exception as e:
        logging.error("Claude usage tracking failed: %s", e)
        return {"success": False, "error": str(e)}


@mcp.tool()
def get_cost_stats(days: int = 7) -> dict[str, Any]:
    """
    Get cost statistics for memory operations.

    Args:
        days: Period in days (default: 7).

    Returns:
        Statistics: operations, tokens, cost.
    """
    try:
        stats = cost_tracker.get_stats(days)
        return {"success": True, "stats": stats}
    except Exception as e:
        logging.error("Cost stats failed: %s", e)
        return {"success": False, "error": str(e)}


@mcp.tool()
def get_cost_stats_by_metadata(
    key: str = "task",
    days: int = 7,
) -> dict[str, Any]:
    """Get cost statistics grouped by metadata[key] (e.g. 'task')."""
    try:
        stats = cost_tracker.get_stats_by_metadata_key(key, days)
        return {
            "success": True,
            "key": key,
            "period_days": days,
            "stats": stats,
        }
    except Exception as e:
        logging.error("Cost metadata stats failed: %s", e)
        return {"success": False, "error": str(e)}


@mcp.tool()
def get_recent_cost_operations(limit: int = 20) -> dict[str, Any]:
    """Get the most recent cost tracker entries for inspection."""
    try:
        operations = cost_tracker.get_recent_operations(limit)
        return {
            "success": True,
            "count": len(operations),
            "operations": operations,
        }
    except Exception as e:
        logging.error("Recent cost operations failed: %s", e)
        return {"success": False, "error": str(e)}


@mcp.tool()
def get_model_breakdown(days: int = 7) -> dict[str, Any]:
    """
    Get cost breakdown by Claude model (Haiku/Sonnet/Opus).

    Shows how much each model consumed — critical for model routing ROI analysis.
    """
    try:
        breakdown = cost_tracker.get_model_breakdown(days)
        return {"success": True, "period_days": days, "models": breakdown}
    except Exception as e:
        logging.error("Model breakdown failed: %s", e)
        return {"success": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Model routing (escalation: Haiku → Sonnet → Opus)
# ---------------------------------------------------------------------------

@mcp.tool()
def deep_reason(
    task: str,
    context: str = "",
    operation_type: str = "deep_reason",
    force_model: str | None = None,
    max_tokens: int = 4096,
) -> dict[str, Any]:
    """
    Delegate a complex task to Claude Sonnet or Opus.

    Called by Claude Code (Haiku) when a task is too complex for the
    lightweight model.  The tool auto-selects the cheapest capable
    model via complexity heuristics, calls the Anthropic API, records
    exact token usage, and returns the result.

    Use this for:
    - Refactoring existing code (>50 lines)
    - Architecture decisions
    - Bug analysis in complex logic
    - Writing new modules from scratch
    - Performance optimisation

    Args:
        task: The task description (what to do).
        context: Relevant code snippets, file contents, or project context.
        operation_type: Cost-tracker operation name.
        force_model: Override auto-routing: 'claude-haiku-4',
            'claude-sonnet-4', or 'claude-opus-4'.
        max_tokens: Max output tokens (default: 4096).

    Returns:
        {
            "success": True,
            "model_used": "claude-opus-4",
            "result": "... Claude response text ...",
            "usage": {input_tokens, output_tokens, ...},
            "cost_estimate": "$0.1234"
        }
    """
    try:
        prompt = f"Context:\n{context}\n\nTask:\n{task}" if context else task

        message = tracked_claude.route_and_complete(
            prompt=prompt,
            operation_type=operation_type,
            context_tokens=len(context.split()) if context else 0,
            max_tokens=max_tokens,
            force_model=force_model,
        )

        # Extract text safely
        content = message.content
        text = ""
        if isinstance(content, list):
            text = "\n".join(
                block.text for block in content
                if hasattr(block, "text")
            )
        elif hasattr(content, "text"):
            text = content.text
        else:
            text = str(content)

        # Build usage summary
        usage = getattr(message, "usage", None)
        usage_summary: dict[str, Any] = {}
        if usage is not None:
            for field in (
                "input_tokens", "output_tokens",
                "cache_creation_input_tokens", "cache_read_input_tokens",
            ):
                val = getattr(usage, field, 0)
                usage_summary[field] = int(val or 0)

        model_used = getattr(message, "model", "unknown")

        return {
            "success": True,
            "model_used": model_used,
            "result": text,
            "usage": usage_summary,
            "finish_reason": getattr(
                getattr(message, "stop_reason", None) or
                getattr(message, "stop_sequence", None),
                "__str__", lambda: "completed",
            )(),
        }

    except Exception as e:
        logging.error("Deep reason failed: %s", e)
        return {
            "success": False,
            "error": str(e),
        }


@mcp.tool()
def routing_report(days: int = 7) -> dict[str, Any]:
    """
    Show model routing cost/usage report.

    Answers: how many calls went through each model, what it cost,
    and whether auto-routing is saving money.

    Args:
        days: Period in days (default: 7).
    """
    try:
        model_breakdown = cost_tracker.get_model_breakdown(days)
        stats_by_task = cost_tracker.get_stats_by_metadata_key("task", days)
        total_stats = cost_tracker.get_stats(days)

        # Estimate what the cost would have been if everything ran on Opus
        opus_price_in = 15.0 / 1_000_000
        opus_price_out = 75.0 / 1_000_000
        hypothetical_opus_cost = (
            total_stats["total_input_tokens"] * opus_price_in
            + total_stats["total_output_tokens"] * opus_price_out
        )
        actual_cost = total_stats["total_cost"]
        savings = hypothetical_opus_cost - actual_cost
        savings_pct = (
            (savings / hypothetical_opus_cost * 100)
            if hypothetical_opus_cost > 0
            else 0.0
        )

        return {
            "success": True,
            "period_days": days,
            "actual_cost": round(actual_cost, 4),
            "hypothetical_opus_only_cost": round(hypothetical_opus_cost, 4),
            "estimated_savings": round(savings, 4),
            "savings_percent": round(savings_pct, 1),
            "by_model": model_breakdown,
            "by_task": {
                k: v for k, v in list(stats_by_task.items())[:15]
            },
        }
    except Exception as e:
        logging.error("Routing report failed: %s", e)
        return {"success": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Resources — direct memory reads
# ---------------------------------------------------------------------------

@mcp.resource("memory://global/handoff")
def get_global_handoff() -> str:
    """Read HOT memory (handoff.md) from global memory."""
    try:
        handoff_path = Path.home() / ".claude" / "memory" / "handoff.md"
        if handoff_path.exists():
            return handoff_path.read_text(encoding='utf-8')
        return "# No handoff data"
    except Exception as e:
        logging.error("Failed to read handoff: %s", e)
        return f"# Error: {e}"


@mcp.resource("memory://global/decisions")
def get_global_decisions() -> str:
    """Read WARM memory (decisions.md) from global memory."""
    try:
        decisions_path = Path.home() / ".claude" / "memory" / "decisions.md"
        if decisions_path.exists():
            return decisions_path.read_text(encoding='utf-8')
        return "# No decisions data"
    except Exception as e:
        logging.error("Failed to read decisions: %s", e)
        return f"# Error: {e}"


if __name__ == "__main__":
    mcp.run()
