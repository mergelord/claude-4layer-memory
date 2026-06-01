#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MCP Server for Claude 4-Layer Memory System

Provides access to memory through Model Context Protocol:
- FTS5 keyword search
- Semantic search
- Memory statistics
- Cost tracking
- Model routing: smart_complete + deep_reason + RoutingLearner
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
from claude_client import TrackedClaudeClient, estimate_complexity  # noqa: E402
from routing_learner import RoutingLearner, get_learner  # noqa: E402

# Initialise MCP server
mcp = FastMCP("claude-4layer-memory")

# Initialise components
fts5_search = L4FTS5Search()
cost_tracker = CostTracker()
tracked_claude = TrackedClaudeClient(cost_tracker=cost_tracker)
routing_learner = get_learner()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_text(message: Any) -> str:
    """Safely extract text content from an Anthropic message response."""
    content = getattr(message, "content", None)
    if content is None:
        return ""
    if isinstance(content, list):
        return "\n".join(
            block.text for block in content if hasattr(block, "text")
        )
    if hasattr(content, "text"):
        return content.text
    return str(content)


def _extract_usage(message: Any) -> dict[str, int]:
    """Extract usage fields from an Anthropic message response."""
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
# FTS5 memory search
# ---------------------------------------------------------------------------

@mcp.tool()
def search_memory(
    query: str,
    limit: int = 10,
    debug: bool = False,
) -> dict[str, Any]:
    """Search memory via FTS5 keyword search."""
    try:
        results = fts5_search.search(query, limit)
        response: dict[str, Any] = {
            "success": True,
            "query": query,
            "count": len(results),
            "results": [
                {"path": r.path, "snippet": r.snippet, "rank": r.rank, "source": r.source}
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
    """Get FTS5 index statistics."""
    try:
        stats = fts5_search.stats()
        return {"success": True, "stats": stats}
    except Exception as e:
        logging.error("Stats failed: %s", e)
        return {"success": False, "error": str(e)}


@mcp.tool()
def reindex_memory() -> dict[str, Any]:
    """Reindex the FTS5 database."""
    try:
        indexed_count = fts5_search.reindex_all()
        return {"success": True, "indexed_files": indexed_count}
    except Exception as e:
        logging.error("Reindex failed: %s", e)
        return {"success": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Cost tracking
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
    """Record exact Claude token usage from an Anthropic API response."""
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
    """Get cost statistics for memory operations."""
    try:
        stats = cost_tracker.get_stats(days)
        return {"success": True, "stats": stats}
    except Exception as e:
        logging.error("Cost stats failed: %s", e)
        return {"success": False, "error": str(e)}


@mcp.tool()
def get_cost_stats_by_metadata(key: str = "task", days: int = 7) -> dict[str, Any]:
    """Get cost statistics grouped by metadata key."""
    try:
        stats = cost_tracker.get_stats_by_metadata_key(key, days)
        return {"success": True, "key": key, "period_days": days, "stats": stats}
    except Exception as e:
        logging.error("Cost metadata stats failed: %s", e)
        return {"success": False, "error": str(e)}


@mcp.tool()
def get_recent_cost_operations(limit: int = 20) -> dict[str, Any]:
    """Get the most recent cost tracker entries."""
    try:
        operations = cost_tracker.get_recent_operations(limit)
        return {"success": True, "count": len(operations), "operations": operations}
    except Exception as e:
        logging.error("Recent cost operations failed: %s", e)
        return {"success": False, "error": str(e)}


@mcp.tool()
def get_model_breakdown(days: int = 7) -> dict[str, Any]:
    """Get cost breakdown by Claude model (Haiku/Sonnet/Opus)."""
    try:
        breakdown = cost_tracker.get_model_breakdown(days)
        return {"success": True, "period_days": days, "models": breakdown}
    except Exception as e:
        logging.error("Model breakdown failed: %s", e)
        return {"success": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Model routing — smart_complete (primary)
# ---------------------------------------------------------------------------

@mcp.tool()
def smart_complete(
    task: str,
    context: str = "",
    operation_type: str = "smart_complete",
    max_tokens: int = 4096,
) -> dict[str, Any]:
    """
    Execute ANY code writing or modification task with auto model selection.

    ALWAYS use this tool instead of writing code yourself when the user
    asks to modify, create, or refactor code.  The tool uses ChromaDB-based
    learning to pick Haiku/Sonnet/Opus automatically.

    Use this for ANY of:
    - Writing new code/functions/modules
    - Modifying existing code
    - Refactoring
    - Fixing bugs
    - Writing tests
    - Any task requiring code output

    Do NOT use this for:
    - Reading files (use Read tool directly)
    - Searching code (use Grep/Glob directly)
    - Simple questions about the project
    - Tasks requiring only a 1-3 line answer

    Args:
        task: Description of what to do.
        context: Relevant code/content for context.
        operation_type: Cost-tracker operation name.
        max_tokens: Max output tokens (default: 4096).

    Returns:
        {"success": True, "model_used": "...", "result": "...", "usage": {...}}
    """
    try:
        prompt = f"Context:\n{context}\n\nTask:\n{task}" if context else task
        context_len = len(context.split()) if context else 0

        # Phase 1: RoutingLearner picks the model
        chosen_model = routing_learner.predict_model(
            task, context_len=context_len, operation_type=operation_type,
        )

        # Phase 2: Call API with chosen model
        message = tracked_claude.complete(
            prompt=prompt,
            model=chosen_model,
            max_tokens=max_tokens,
            operation_type=operation_type,
            cost_metadata={"routing": "smart_complete", "task": task[:120]},
        )

        usage = _extract_usage(message)

        # Phase 3: Record outcome for learning (assume success)
        cost_est = (
            usage.get("input_tokens", 0) / 1_000_000 * 0.25
            + usage.get("output_tokens", 0) / 1_000_000 * 1.25
        )
        routing_learner.record_outcome(
            task=task,
            model_used=chosen_model,
            was_successful=True,
            operation_type=operation_type,
            tokens={"input": usage.get("input_tokens", 0), "output": usage.get("output_tokens", 0)},
            cost_usd=cost_est,
        )

        return {
            "success": True,
            "model_used": chosen_model,
            "routing_phase": routing_learner.stats().get("routing_phase", "unknown"),
            "result": _extract_text(message),
            "usage": usage,
        }

    except Exception as e:
        logging.error("smart_complete failed: %s", e)
        return {"success": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Model routing — deep_reason (architecture / hard problems)
# ---------------------------------------------------------------------------

@mcp.tool()
def deep_reason(
    task: str,
    context: str = "",
    force_model: str | None = None,
    max_tokens: int = 4096,
) -> dict[str, Any]:
    """
    Delegate a complex reasoning task to Sonnet or Opus.

    Use this for architecture decisions, root cause analysis, and complex
    reasoning where Opus-level thinking is required.

    Args:
        task: The task description.
        context: Relevant code/content for context.
        force_model: Override auto-routing.
        max_tokens: Max output tokens.
    """
    try:
        prompt = f"Context:\n{context}\n\nTask:\n{task}" if context else task

        message = tracked_claude.route_and_complete(
            prompt=prompt,
            operation_type="deep_reason",
            context_tokens=len(context.split()) if context else 0,
            max_tokens=max_tokens,
            force_model=force_model or "claude-opus-4",
        )

        return {
            "success": True,
            "model_used": getattr(message, "model", "unknown"),
            "result": _extract_text(message),
            "usage": _extract_usage(message),
        }

    except Exception as e:
        logging.error("deep_reason failed: %s", e)
        return {"success": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Routing analytics
# ---------------------------------------------------------------------------

@mcp.tool()
def routing_report(days: int = 7) -> dict[str, Any]:
    """Show model routing cost/usage report with savings estimate."""
    try:
        model_breakdown = cost_tracker.get_model_breakdown(days)
        stats_by_task = cost_tracker.get_stats_by_metadata_key("task", days)
        total_stats = cost_tracker.get_stats(days)
        learner_stats = routing_learner.stats()

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
            if hypothetical_opus_cost > 0 else 0.0
        )

        return {
            "success": True,
            "period_days": days,
            "actual_cost": round(actual_cost, 4),
            "hypothetical_opus_only_cost": round(hypothetical_opus_cost, 4),
            "estimated_savings": round(savings, 4),
            "savings_percent": round(savings_pct, 1),
            "by_model": model_breakdown,
            "by_task": {k: v for k, v in list(stats_by_task.items())[:15]},
            "learner": learner_stats,
        }
    except Exception as e:
        logging.error("Routing report failed: %s", e)
        return {"success": False, "error": str(e)}


@mcp.tool()
def routing_learner_stats() -> dict[str, Any]:
    """Get RoutingLearner statistics: cold start vs trained, success rates."""
    try:
        return {"success": True, **routing_learner.stats()}
    except Exception as e:
        logging.error("Learner stats failed: %s", e)
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
