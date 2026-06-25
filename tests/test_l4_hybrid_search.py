#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the programmatic hybrid_search() return-value API."""

from __future__ import annotations

import importlib
import sys
import threading
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from l4_fts5_search import SearchResult  # noqa: E402  pylint: disable=wrong-import-position
from ranking import make_join_key  # noqa: E402  pylint: disable=wrong-import-position


@pytest.fixture(name="module")
def fixture_module():
    """Provide the hybrid API module under test."""
    return importlib.import_module("l4_hybrid_search")


def _make_search_result(source: str, rel_path: str, snippet="snippet") -> Any:
    """Build an l4_fts5_search.SearchResult for fake FTS streams."""
    return SearchResult(
        path=f"[{source}] {rel_path}",
        key=make_join_key(source, rel_path),
        snippet=snippet,
        rank=-1.0,
        source="fts5",
    )


def test_hybrid_search_returns_merged_ranking(module, monkeypatch):
    """hybrid_search() must return RankedResult entries, not print stdout."""
    fts_mock = MagicMock(spec=module.L4FTS5Search)
    fts_mock.search.return_value = [
        _make_search_result("global", "notes.md", snippet="alpha fts")
    ]
    semantic_results = [
        {"key": "[global] notes.md", "text": "alpha sem", "distance": 0.1, "rank": 0}
    ]

    monkeypatch.setattr(
        module.l4_hybrid_runtime,
        "fetch_semantic_results",
        lambda query: semantic_results,
    )
    monkeypatch.setattr(
        module.l4_hybrid_runtime.l4_fts5_search,
        "fetch_bm25_results",
        None,
    )
    rerank_lookup = MagicMock(return_value=None)
    monkeypatch.setattr(module.l4_hybrid_runtime, "get_l4_reranker", rerank_lookup)

    merged = module.hybrid_search(fts_mock, "alpha", enable_rerank=False)

    assert len(merged) == 1
    entry = merged[0]
    assert entry.key == make_join_key("global", "notes.md")
    assert set(entry.sources.keys()) == {"fts", "semantic"}
    assert entry.normalized_score == 1.0
    assert rerank_lookup.call_count == 0


def test_hybrid_search_returns_empty_when_no_engine_has_hits(module, monkeypatch):
    """No FTS/semantic/BM25 hits -> [] for programmatic callers."""
    fts_mock = MagicMock(spec=module.L4FTS5Search)
    fts_mock.search.return_value = []

    monkeypatch.setattr(module.l4_hybrid_runtime, "fetch_semantic_results", lambda query: [])
    monkeypatch.setattr(
        module.l4_hybrid_runtime.l4_fts5_search,
        "fetch_bm25_results",
        None,
    )

    assert module.hybrid_search(fts_mock, "nothing", enable_rerank=False) == []


def test_hybrid_search_fetches_sources_in_parallel(module, monkeypatch):
    """FTS, semantic, and BM25 fetches must start concurrently."""
    fts_mock = MagicMock(spec=module.L4FTS5Search)
    barrier = threading.Barrier(3, timeout=2)
    started: list[str] = []
    started_lock = threading.Lock()

    def wait_for_other_sources(source_name: str) -> None:
        with started_lock:
            started.append(source_name)
        barrier.wait(timeout=2)

    def fake_fts_search(query, limit=20):  # noqa: ARG001
        wait_for_other_sources("fts")
        return []

    def fake_semantic(query):  # noqa: ARG001
        wait_for_other_sources("semantic")
        return []

    def fake_bm25(query):  # noqa: ARG001
        wait_for_other_sources("bm25")
        return []

    fts_mock.search.side_effect = fake_fts_search
    monkeypatch.setattr(module.l4_hybrid_runtime, "fetch_semantic_results", fake_semantic)
    monkeypatch.setattr(
        module.l4_hybrid_runtime.l4_fts5_search,
        "fetch_bm25_results",
        fake_bm25,
    )

    assert module.hybrid_search(fts_mock, "alpha", enable_rerank=False) == []
    assert set(started) == {"fts", "semantic", "bm25"}


def test_fetch_semantic_results_reuses_in_process_backend(module, monkeypatch):
    """Runtime semantic fetches must cache the backend after first use."""
    runtime = module.l4_hybrid_runtime
    created_backends = []

    class FakeSemanticBackend:  # pylint: disable=too-few-public-methods
        def __init__(self):
            self.queries: list[str] = []
            created_backends.append(self)

        def search_all(self, query):
            self.queries.append(query)
            return [
                {
                    "key": make_join_key("global", f"{query}.md"),
                    "text": f"semantic {query}",
                    "distance": 0.1,
                    "metadata": {"file": f"{query}.md"},
                    "source": "global",
                }
            ]

    monkeypatch.setattr(runtime, "_semantic_backend", None)
    monkeypatch.setattr(runtime, "_new_semantic_backend", FakeSemanticBackend)

    first = runtime.fetch_semantic_results("first")
    second = runtime.fetch_semantic_results("second")

    assert len(created_backends) == 1
    assert created_backends[0].queries == ["first", "second"]
    assert first[0]["text"] == "semantic first"
    assert second[0]["text"] == "semantic second"


def test_fetch_semantic_results_failure_degrades_to_empty(module, monkeypatch):
    """Semantic backend failures must not break hybrid runtime callers."""
    runtime = module.l4_hybrid_runtime

    class BrokenSemanticBackend:  # pylint: disable=too-few-public-methods
        def search_all(self, query):  # noqa: ARG002
            raise RuntimeError("semantic boom")

    monkeypatch.setattr(runtime, "_semantic_backend", BrokenSemanticBackend())

    assert runtime.fetch_semantic_results("hello") == []
