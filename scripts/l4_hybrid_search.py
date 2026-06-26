#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# mypy: ignore-errors
# pylint: disable=wrong-import-position,import-error
"""Programmatic hybrid search API for repository/runtime callers.

This module exposes the return-value counterpart to the CLI-only
``l4_fts5_search.py hybrid`` command. The merge/rerank implementation lives in
``l4_hybrid_runtime`` so MCP/runtime callers do not reach into CLI internals
from this public wrapper.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import l4_hybrid_runtime  # noqa: E402
from l4_fts5_search import L4FTS5Search  # noqa: E402


def hybrid_search(
    fts: L4FTS5Search, query: str, *, enable_rerank: bool = True
) -> list[Any]:
    """Return hybrid search results instead of printing CLI output.

    Combines FTS5, semantic search, and optional BM25 via RRF, preserving the
    existing document-level key contract and optional cross-encoder reranking.
    This is the programmatic API used by the MCP ``hybrid_search_memory`` tool.
    """
    return l4_hybrid_runtime.build_hybrid_results(
        fts,
        query,
        enable_rerank=enable_rerank,
    )


def hybrid_search_timed(
    fts: L4FTS5Search, query: str, *, enable_rerank: bool = True
) -> tuple[list[Any], dict[str, Any]]:
    """Return ``(results, timing_metadata)`` for hybrid search.

    Timing-aware counterpart to :func:`hybrid_search`; delegates to
    ``l4_hybrid_runtime.build_hybrid_results_timed`` so the MCP layer can expose
    optional per-stage latency (fetch/merge/rerank) without duplicating the
    retrieval flow. ``hybrid_search`` remains the untimed default path.
    """
    return l4_hybrid_runtime.build_hybrid_results_timed(
        fts,
        query,
        enable_rerank=enable_rerank,
    )
