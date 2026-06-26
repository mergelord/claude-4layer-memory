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

import os
import sys
import logging
import threading
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
from l4_hybrid_search import hybrid_search, hybrid_search_timed  # noqa: E402
from l4_logging import configure_logging  # noqa: E402
from cost_tracker import (  # noqa: E402
    CACHE_CREATION_PRICE_KEY,
    CACHE_READ_PRICE_KEY,
    CostTracker,
)
from claude_client import TrackedClaudeClient, approx_tokens  # noqa: E402
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


def _prewarm_semantic_model() -> None:
    """Warm the in-process semantic backend in a background daemon thread.

    Loading sentence-transformers + Chroma lazily on the first hybrid query
    adds multi-second latency to that query. When the server runs as a
    long-lived process we kick off a best-effort background warm-up so the
    model is ready before the first real request. Any failure is logged and the
    server continues (the first query just pays the lazy-load cost as before).

    The work is imported and started lazily here -- never at module import time
    -- so importing ``mcp_server`` (e.g. in tests) stays side-effect free and
    fast.
    """
    def _worker() -> None:
        try:
            from l4_hybrid_runtime import prewarm_semantic_backend

            prewarm_semantic_backend()
        except Exception as exc:  # noqa: BLE001
            logging.warning("Semantic prewarm failed: %s", exc)

    thread = threading.Thread(
        target=_worker, name="semantic-prewarm", daemon=True
    )
    thread.start()


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
def hybrid_search_memory(
    query: str,
    limit: int = 10,
    rerank: bool = True,
    debug: bool = False,
) -> dict[str, Any]:
    """Search memory via hybrid retrieval (FTS5 + semantic + BM25 + RRF).

    Unlike ``search_memory`` (FTS5 keyword search only), this uses the full
    hybrid pipeline and returns structured ranking metadata suitable for MCP
    clients. Set ``debug=True`` to additionally include a ``meta`` block with
    per-stage timing (fetch/merge/rerank, in ms); the default path is unchanged.
    """
    try:
        if debug:
            merged, timing = hybrid_search_timed(
                fts5_search, query, enable_rerank=rerank
            )
        else:
            merged = hybrid_search(fts5_search, query, enable_rerank=rerank)

        results = []
        for entry in merged[:limit]:
            sources = sorted(entry.sources.keys())
            snippet = ""
            for source_name in sources:
                for hit in entry.sources[source_name]:
                    snippet = (hit.get("snippet") or hit.get("text") or "").strip()
                    if snippet:
                        break
                if snippet:
                    break

            results.append(
                {
                    "key": entry.key,
                    "score": entry.score,
                    "normalized_score": entry.normalized_score,
                    "sources": sources,
                    "snippet": snippet[:200],
                }
            )

        response: dict[str, Any] = {
            "success": True,
            "query": query,
            "count": len(results),
            "results": results,
        }
        if debug:
            response["meta"] = {
                "engine": "hybrid",
                "rerank": rerank,
                "limit": limit,
                "total_candidates": len(merged),
                "timing_ms": timing,
            }
        return response
    except Exception as e:
        logging.error("Hybrid search failed: %s", e)
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
) -> dict[str,