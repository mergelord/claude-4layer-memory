#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Shared return-value hybrid search runtime.

This module centralizes the non-printing hybrid search flow used by runtime
callers. It keeps the existing retrieval strategy intact: FTS5 + semantic
backend + optional BM25, RRF merge, score normalization, and optional
cross-encoder reranking.
"""

from __future__ import annotations

import logging
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from threading import Lock
from typing import Any, Iterator, Optional

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

# The imports below intentionally run after the sys.path bootstrap above so the
# flat ``scripts/`` modules resolve at runtime without an installed package.
# Pylint analyzes statically (no bootstrap) and cannot resolve these sibling
# modules, so suppress only the import-position and unresolved-import checks for
# this shim rather than disabling the whole file (mirrors l4_hybrid_search.py).
# pylint: disable=wrong-import-position,import-error
import l4_fts5_search  # noqa: E402
from l4_fts5_search import L4FTS5Search  # noqa: E402

_semantic_backend: Optional[Any] = None  # pylint: disable=invalid-name
_semantic_backend_lock = Lock()
_MODEL_LOAD_LOGGERS = (
    "huggingface_hub",
    "httpx",
    "sentence_transformers",
    "transformers",
    "urllib3",
)
_QUIET_MODEL_LOAD_ENV = {
    "HF_HUB_DISABLE_PROGRESS_BARS": "1",
    "HF_HUB_DISABLE_TELEMETRY": "1",
    "HUGGINGFACE_HUB_VERBOSITY": "error",
    "TOKENIZERS_PARALLELISM": "false",
    "TRANSFORMERS_VERBOSITY": "error",
}
_OFFLINE_MODEL_LOAD_ENV = {
    "HF_HUB_OFFLINE": "1",
    "TRANSFORMERS_OFFLINE": "1",
}


@contextmanager
def _temporary_env(updates: dict[str, str]) -> Iterator[None]:
    """Temporarily set environment variables and restore them afterwards."""
    previous = {key: os.environ.get(key) for key in updates}
    os.environ.update(updates)
    try:
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


@contextmanager
def _quiet_model_load_context(*, offline: bool) -> Iterator[None]:
    """Suppress noisy Hugging Face/model-load logs for MCP runtime searches."""
    env_updates = dict(_QUIET_MODEL_LOAD_ENV)
    if offline:
        env_updates.update(_OFFLINE_MODEL_LOAD_ENV)

    loggers = [logging.getLogger(name) for name in _MODEL_LOAD_LOGGERS]
    previous_levels = [logger.level for logger in loggers]
    for logger in loggers:
        logger.setLevel(logging.ERROR)

    try:
        with _temporary_env(env_updates):
            yield
    finally:
        for logger, level in zip(loggers, previous_levels):
            logger.setLevel(level)


def _new_global_semantic_memory() -> Any:
    """Create the underlying semantic memory backend lazily."""
    from l4_semantic_global import GlobalSemanticMemory

    return GlobalSemanticMemory()


class _QuietOfflineSemanticBackend:
    """Runtime semantic backend with quiet offline-first model loading.

    MCP hybrid search should avoid Hugging Face network probes when the model is
    already cached locally. The first semantic query therefore tries an offline
    model load under quiet logging. If the cache is cold, it retries once online
    while keeping the same log suppression so MCP stdio stays clean.
    """

    def __init__(self) -> None:
        self._backend = _new_global_semantic_memory()

    def search_all(self, query: str) -> list[dict[str, Any]]:
        if getattr(self._backend, "_model", None) is not None:
            return self._backend.search_all(query)

        try:
            with _quiet_model_load_context(offline=True):
                return self._backend.search_all(query)
        except Exception as exc:  # noqa: BLE001
            if getattr(self._backend, "_model", None) is not None:
                raise
            l4_fts5_search.logging.info(
                "Offline semantic model load missed local cache; retrying online: %s",
                exc,
            )

        with _quiet_model_load_context(offline=False):
            return self._backend.search_all(query)


def _new_semantic_backend() -> Any:
    """Create a semantic memory backend lazily to avoid MCP startup cost."""
    return _QuietOfflineSemanticBackend()


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


def prewarm_semantic_backend() -> bool:
    """Eagerly construct and warm the in-process semantic backend.

    Loading ``sentence_transformers`` + Chroma lazily on the first hybrid query
    adds multi-second latency to that query. For long-lived servers a caller can
    invoke this once at startup (e.g. from a background thread) so the model and
    Chroma client are ready before the first real request.

    Best-effort: a tiny throwaway query triggers the load; any failure (cold
    cache, missing optional deps, offline) is logged and reported as ``False``
    so the caller never crashes — the first real query simply pays the lazy-load
    cost as before.
    """
    try:
        _get_semantic_backend().search_all("__prewarm__")
        return True
    except Exception as exc:  # noqa: BLE001
        l4_fts5_search.logging.info("Semantic prewarm skipped: %s", exc)
        return False


def get_l4_reranker():
    """Return the optional L4 reranker, preserving lazy import semantics."""
    return l4_fts5_search._get_l4_rerank()  # pylint: disable=protected-access


def _fetch_bm25_results(query: str) -> list[Any]:
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

    Stream construction and RRF merge are delegated to the single source of
    truth in :mod:`l4_fts5_search` (``build_hybrid_streams`` +
    ``rrf_merge_streams``) so the runtime, sequential, and parallel paths all
    produce identical streams. Reranking stays here so callers keep control of
    ``enable_rerank``.
    """
    fts_results, semantic_results, bm25_results = _fetch_source_results(fts, query)

    fts_stream, semantic_stream, bm25_stream = l4_fts5_search.build_hybrid_streams(
        fts_results, semantic_results, bm25_results
    )

    if not fts_stream and not semantic_stream and not bm25_stream:
        return []

    merged = l4_fts5_search.rrf_merge_streams(
        fts_stream, semantic_stream, bm25_stream
    )

    reranker = get_l4_reranker() if enable_rerank and merged else None
    if reranker is not None:
        merged = reranker(query, merged[:20])

    return merged
