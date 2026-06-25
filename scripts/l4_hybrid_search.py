#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# mypy: ignore-errors
# pylint: disable=protected-access,wrong-import-position
"""Programmatic hybrid search API for repository/runtime callers.

This module exposes the return-value counterpart to the CLI-only
``l4_fts5_search.py hybrid`` command. It deliberately reuses the current
``l4_fts5_search`` implementation pieces (semantic subprocess with timeout,
BM25 optional fan-out, RRF, optional rerank) instead of changing the runtime
strategy in this PR.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import l4_fts5_search  # noqa: E402
from l4_fts5_search import L4FTS5Search  # noqa: E402
from ranking import normalize_existing_key, normalize_scores, rrf_merge  # noqa: E402


def _fetch_semantic(query: str) -> list[dict[str, Any]]:
    """Fetch semantic hits using the current CLI-backed implementation."""
    return l4_fts5_search._fetch_semantic_results(query)


def _get_reranker():
    """Return the optional L4 reranker, preserving lazy import semantics."""
    return l4_fts5_search._get_l4_rerank()


def hybrid_search(
    fts: L4FTS5Search, query: str, *, enable_rerank: bool = True
) -> list[Any]:
    """Return hybrid search results instead of printing CLI output.

    Combines FTS5, semantic search, and optional BM25 via RRF, preserving the
    existing document-level key contract and optional cross-encoder reranking.
    This is the programmatic API used by the MCP ``hybrid_search_memory`` tool.

    Args:
        fts: Initialized FTS5 search engine instance.
        query: User search query.
        enable_rerank: Whether to apply the optional cross-encoder reranker.

    Returns:
        A list of ``ranking.RankedResult``-like objects. Returns ``[]`` when no
        engine produced a hit. Engine-specific failures keep the same behaviour
        as the underlying helpers: semantic/BM25 degrade to no hits, while an
        FTS failure propagates to the caller and is handled by the MCP wrapper.
    """
    fts_results = fts.search(query, limit=20)
    semantic_results = _fetch_semantic(query)

    bm25_results: list[dict[str, Any]] = []
    if l4_fts5_search.fetch_bm25_results is not None:
        try:
            bm25_results = l4_fts5_search.fetch_bm25_results(query)
        except Exception as exc:  # noqa: BLE001
            l4_fts5_search.logging.warning("BM25 search failed: %s", exc)

    fts_stream = [
        {
            "key": res.key,
            "display_path": res.path,
            "snippet": res.snippet,
            "rank": res.rank,
            "source_type": "fts",
        }
        for res in fts_results
    ]

    semantic_stream = [
        {
            **hit,
            "key": normalize_existing_key(hit.get("key", "")),
            "source_type": "semantic",
        }
        for hit in semantic_results
    ]

    bm25_stream = [
        {
            "key": normalize_existing_key(item["key"]),
            "snippet": item["snippet"],
            "rank": item.get("rank", 0),
            "bm25_score": item.get("bm25_score"),
            "source_type": "bm25",
        }
        for item in bm25_results
    ]

    fts_stream = l4_fts5_search.collapse_to_best_per_doc(fts_stream)
    semantic_stream = l4_fts5_search.collapse_to_best_per_doc(semantic_stream)
    bm25_stream = l4_fts5_search.collapse_to_best_per_doc(bm25_stream)

    if not fts_stream and not semantic_stream and not bm25_stream:
        return []

    merged = normalize_scores(
        rrf_merge(
            ("fts", fts_stream),
            ("semantic", semantic_stream),
            ("bm25", bm25_stream),
        )
    )

    reranker = _get_reranker() if enable_rerank and merged else None
    if reranker is not None:
        merged = reranker(query, merged[:20])

    return merged
