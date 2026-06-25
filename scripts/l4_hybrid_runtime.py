#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# mypy: ignore-errors
# pylint: disable=wrong-import-position,import-error,protected-access,broad-exception-caught,import-outside-toplevel
"""Shared return-value hybrid search runtime.

This module centralizes the non-printing hybrid search flow used by runtime
callers. It keeps the existing retrieval strategy intact: FTS5 + semantic
backend + optional BM25, RRF merge, score normalization, and optional
cross-encoder reranking.
"""

from __future__ import annotations

import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Lock
from typing import Any

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import l4_fts5_search  # noqa: E402
from l4_fts5_search import L4FTS5Search  # noqa: E402
from ranking import normalize_existing_key, normalize_scores, rrf_merge  # noqa: E402

_semantic_backend: Any | None = None
_semantic_backend_lock = Lock()


def _new_semantic_backend() -> Any:
    """Create a semantic memory backend lazily to avoid MCP startup cost."""
    from l4_semantic_global import GlobalSemanticMemory

    return GlobalSemanticMemory()


def _get_semantic_backend() -> Any:
    """Return a cached in-process semantic backend for runtime callers."""
    global _semantic_backend  # pylint: disable=global-statement
    if _semantic_backend is None:
        with _semantic_backend_lock:
            if _semantic_backend is None:
                _semantic_backend = _new_semantic_backend()
    return _semantic_backend


def fetch_semantic_results(query: str) -> list[dict[str, Any]]:
    """Fetch semantic hits through a cached in-process backend.

    The previous runtime path spawned ``l4_semantic_global.py`` for every MCP
    hybrid query, paying the full ``sentence_transformers`` import/model-load
    cost every time. Keeping ``GlobalSemanticMemory`` in this process preserves
    lazy startup while allowing subsequent MCP queries to reuse the loaded
    model and Chroma client.
    """
    try:
        results = _get_semantic_backend().search_all(query)
    except Exception as exc:  # noqa: BLE001
        l4_fts5_search.logging.warning("Semantic search failed: %s", exc)
        return []

    return results if isinstance(results, list) else []


def get_l4_reranker():
    """Return the optional L4 reranker, preserving lazy import semantics."""
    return l4_fts5_search._get_l4_rerank()


def _fetch_bm25_results(query: str) -> list[dict[str, Any]]:
    """Fetch optional BM25 hits, degrading to no hits on BM25 failures."""
    if l4_fts5_search.fetch_bm25_results is None:
        return []

    try:
        return l4_fts5_search.fetch_bm25_results(query)
    except Exception as exc:  # noqa: BLE001
        l4_fts5_search.logging.warning("BM25 search failed: %s", exc)
        return []


def _fetch_source_results(
    fts: L4FTS5Search, query: str
) -> tuple[list[Any], list[dict[str, Any]], list[dict[str, Any]]]:
    """Fetch FTS, semantic, and BM25 result streams concurrently."""
    with ThreadPoolExecutor(max_workers=3) as executor:
        future_fts = executor.submit(fts.search, query, limit=20)
        future_semantic = executor.submit(fetch_semantic_results, query)
        future_bm25 = executor.submit(_fetch_bm25_results, query)

        fts_results = future_fts.result()
        semantic_results = future_semantic.result()
        bm25_results = future_bm25.result()

    return fts_results, semantic_results, bm25_results


def _build_fts_stream(fts_results: list[Any]) -> list[dict[str, Any]]:
    """Convert FTS SearchResult entries into RRF stream items."""
    return [
        {
            "key": res.key,
            "display_path": res.path,
            "snippet": res.snippet,
            "rank": res.rank,
            "source_type": "fts",
        }
        for res in fts_results
    ]


def _build_semantic_stream(
    semantic_results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Convert semantic hits into normalized RRF stream items."""
    return [
        {
            **hit,
            "key": normalize_existing_key(hit.get("key", "")),
            "source_type": "semantic",
        }
        for hit in semantic_results
    ]


def _build_bm25_stream(bm25_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert BM25 hits into normalized RRF stream items."""
    return [
        {
            "key": normalize_existing_key(item["key"]),
            "snippet": item["snippet"],
            "rank": item.get("rank", 0),
            "bm25_score": item.get("bm25_score"),
            "source_type": "bm25",
        }
        for item in bm25_results
    ]


def build_hybrid_results(
    fts: L4FTS5Search, query: str, *, enable_rerank: bool = True
) -> list[Any]:
    """Return merged hybrid search results without printing CLI output.

    Args:
        fts: Initialized FTS5 search engine instance.
        query: User search query.
        enable_rerank: Whether to apply the optional cross-encoder reranker.

    Returns:
        A list of ``ranking.RankedResult``-like objects. Returns ``[]`` when no
        engine produced a hit. Semantic/BM25 failures degrade to no hits via
        their existing helper boundaries; FTS failures propagate to callers.
    """
    fts_results, semantic_results, bm25_results = _fetch_source_results(fts, query)

    fts_stream = l4_fts5_search.collapse_to_best_per_doc(
        _build_fts_stream(fts_results)
    )
    semantic_stream = l4_fts5_search.collapse_to_best_per_doc(
        _build_semantic_stream(semantic_results)
    )
    bm25_stream = l4_fts5_search.collapse_to_best_per_doc(
        _build_bm25_stream(bm25_results)
    )

    if not fts_stream and not semantic_stream and not bm25_stream:
        return []

    merged = normalize_scores(
        rrf_merge(
            ("fts", fts_stream),
            ("semantic", semantic_stream),
            ("bm25", bm25_stream),
        )
    )

    reranker = get_l4_reranker() if enable_rerank and merged else None
    if reranker is not None:
        merged = reranker(query, merged[:20])

    return merged
