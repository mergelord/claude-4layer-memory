#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Real tests for cmd_hybrid_parallel() and CLI flag parsing in l4_fts5_search.

The previous version of this file was a stale snapshot of scripts/l4_fts5_search.py
with no test_* functions — pytest collected zero tests, which masked a regression
risk in the parallel hybrid search code path. These tests exercise the actual
target module via importlib and stub out all external collaborators (FTS engine,
semantic engine, BM25 module, cross-encoder reranker) with deterministic
fakes, so the suite can run with no DB, no network, and no model weights.
"""
from __future__ import annotations

import importlib
import logging
import sqlite3
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest


SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


# pylint: disable-next=wrong-import-position,import-error
from ranking import make_join_key  # noqa: E402


@pytest.fixture(name="module")
def fixture_module():
    """Provide the freshly imported target module under test."""
    return importlib.import_module("l4_fts5_search")


def _make_search_result(
    module: Any,
    source: str,
    rel_path: str,
    snippet: str = "snippet",
    rank: float = -3.0,
) -> Any:
    """Build a SearchResult whose key matches production normalisation."""
    return module.SearchResult(
        path=f"[{source}] {rel_path}",
        key=make_join_key(source, rel_path),
        snippet=snippet,
        rank=rank,
        source="fts5",
    )


def _patch_streams(
    monkeypatch,
    module,
    *,
    fts_results=None,
    fts_side_effect=None,
    semantic_results=None,
    bm25_results=None,
    reranker_lookup=None,
):
    """Patch every external collaborator used by cmd_hybrid_parallel.

    Returns the L4FTS5Search mock so individual tests can inspect calls if
    needed. ``reranker_lookup`` should be a callable replacing
    ``_get_l4_rerank``; default is a MagicMock returning ``None`` so tests
    can also assert it was *not* called.
    """
    fts_mock = MagicMock(spec=module.L4FTS5Search)
    if fts_side_effect is not None:
        fts_mock.search.side_effect = fts_side_effect
    else:
        fts_mock.search.return_value = fts_results or []

    semantic_payload = semantic_results or []

    def fake_fetch_semantic(query, timeout=30):  # noqa: ARG001
        return semantic_payload

    monkeypatch.setattr(module, "_fetch_semantic_results", fake_fetch_semantic)

    if bm25_results is None:
        monkeypatch.setattr(module, "fetch_bm25_results", None)
    else:
        bm25_payload = bm25_results

        def fake_bm25(query):  # noqa: ARG001
            return bm25_payload

        monkeypatch.setattr(module, "fetch_bm25_results", fake_bm25)

    if reranker_lookup is None:
        reranker_lookup = MagicMock(return_value=None)
    monkeypatch.setattr(module, "_get_l4_rerank", reranker_lookup)
    return fts_mock, reranker_lookup


# ---------------------------------------------------------------------------
# 1. End-to-end: three engines merge and the printed output reflects all of
#    them.
# ---------------------------------------------------------------------------


def test_cmd_hybrid_parallel_merges_fts_semantic_bm25_and_prints_sources(
    module, monkeypatch, capsys
):
    fts_results = [
        _make_search_result(module, "global", "notes.md", snippet="alpha fts", rank=-1.0)
    ]
    semantic_results = [
        {"key": "[global] notes.md", "text": "alpha semantic", "distance": 0.1, "rank": 0}
    ]
    bm25_results = [
        {"key": "[global] notes.md", "snippet": "alpha bm25", "rank": 0, "bm25_score": 1.23}
    ]

    fts_mock, _ = _patch_streams(
        monkeypatch,
        module,
        fts_results=fts_results,
        semantic_results=semantic_results,
        bm25_results=bm25_results,
    )

    module.cmd_hybrid_parallel(fts_mock, "alpha", enable_rerank=False)

    out = capsys.readouterr().out
    assert "[HYBRID SEARCH - PARALLEL] 'alpha'" in out
    assert "Fetch time:" in out
    assert "Merge time:" in out
    assert "Total time:" in out
    assert "Merged 1 unique result(s)" in out
    # All three engines must appear on the single merged-result line.
    contributors_lines = [line for line in out.splitlines() if "sources=" in line]
    assert contributors_lines, "Expected at least one merged-result line"
    assert "sources=[bm25, fts, semantic]" in contributors_lines[0]


# ---------------------------------------------------------------------------
# 2. Semantic / BM25 keys with dashed source names must be normalised onto
#    the FTS key so RRF actually merges them.
# ---------------------------------------------------------------------------


def test_cmd_hybrid_parallel_normalizes_semantic_and_bm25_keys(
    module, monkeypatch, capsys
):
    # FTS uses already-normalised source ("my-project" → "my_project").
    fts_results = [_make_search_result(module, "my-project", "notes.md")]
    # Semantic and BM25 still ship the raw dashed bracket — production
    # normalisation must coerce them onto the same join key.
    semantic_results = [
        {"key": "[my-project] notes.md", "text": "sem", "distance": 0.2, "rank": 0}
    ]
    bm25_results = [
        {"key": "[my-project] notes.md", "snippet": "bm", "rank": 0, "bm25_score": 0.5}
    ]

    fts_mock, _ = _patch_streams(
        monkeypatch,
        module,
        fts_results=fts_results,
        semantic_results=semantic_results,
        bm25_results=bm25_results,
    )

    module.cmd_hybrid_parallel(fts_mock, "x", enable_rerank=False)

    out = capsys.readouterr().out
    assert "Merged 1 unique result(s)" in out
    # Normalised key wins; the raw dashed bracket must never appear as the
    # merged-key header.
    assert "[my_project] notes.md" in out
    result_line = next(line for line in out.splitlines() if "sources=" in line)
    assert "[my-project]" not in result_line
    assert "sources=[bm25, fts, semantic]" in result_line


# ---------------------------------------------------------------------------
# 3. Multiple chunks of the same doc from the same engine collapse to one
#    best hit (semantic → min distance).
# ---------------------------------------------------------------------------


def test_cmd_hybrid_parallel_collapses_duplicate_chunks_per_engine(
    module, monkeypatch, capsys
):
    semantic_results = [
        {"key": "[global] notes.md", "text": "chunk-A", "distance": 0.5, "rank": 0},
        {"key": "[global] notes.md", "text": "chunk-B-best", "distance": 0.1, "rank": 1},
        {"key": "[global] notes.md", "text": "chunk-C", "distance": 0.4, "rank": 2},
    ]

    fts_mock, _ = _patch_streams(
        monkeypatch,
        module,
        fts_results=[],
        semantic_results=semantic_results,
        bm25_results=[],
    )

    module.cmd_hybrid_parallel(fts_mock, "alpha", enable_rerank=False)

    out = capsys.readouterr().out
    assert "Merged 1 unique result(s)" in out
    assert "chunk-B-best" in out
    assert "chunk-A" not in out
    assert "chunk-C" not in out


# ---------------------------------------------------------------------------
# 4. If one engine raises, the others still drive the merged output.
# ---------------------------------------------------------------------------


def test_cmd_hybrid_parallel_engine_failure_degrades_to_remaining_streams(
    module, monkeypatch, capsys
):
    semantic_results = [
        {"key": "[global] notes.md", "text": "ok-sem", "distance": 0.2, "rank": 0}
    ]
    bm25_results = [
        {"key": "[global] notes.md", "snippet": "ok-bm", "rank": 0, "bm25_score": 0.5}
    ]

    fts_mock, _ = _patch_streams(
        monkeypatch,
        module,
        fts_side_effect=RuntimeError("fts engine boom"),
        semantic_results=semantic_results,
        bm25_results=bm25_results,
    )

    module.cmd_hybrid_parallel(fts_mock, "alpha", enable_rerank=False)

    out = capsys.readouterr().out
    assert "Merged 1 unique result(s)" in out
    result_line = next(line for line in out.splitlines() if "sources=" in line)
    assert "sources=[bm25, semantic]" in result_line
    assert "fts" not in result_line


# ---------------------------------------------------------------------------
# 5. All engines empty → explicit empty-result message and no merge line.
# ---------------------------------------------------------------------------


def test_cmd_hybrid_parallel_no_results_prints_empty_message(
    module, monkeypatch, capsys
):
    fts_mock, _ = _patch_streams(
        monkeypatch,
        module,
        fts_results=[],
        semantic_results=[],
        bm25_results=[],
    )

    module.cmd_hybrid_parallel(fts_mock, "nothing here", enable_rerank=False)

    out = capsys.readouterr().out
    assert "No results from any engine." in out
    assert "Merged" not in out


# ---------------------------------------------------------------------------
# 6. enable_rerank=False short-circuits the lazy reranker lookup entirely.
# ---------------------------------------------------------------------------


def test_cmd_hybrid_parallel_no_rerank_does_not_import_reranker(
    module, monkeypatch
):
    fts_results = [_make_search_result(module, "global", "notes.md")]
    rerank_lookup = MagicMock(return_value=None)

    fts_mock, _ = _patch_streams(
        monkeypatch,
        module,
        fts_results=fts_results,
        semantic_results=[],
        bm25_results=None,  # BM25 module unavailable
        reranker_lookup=rerank_lookup,
    )

    module.cmd_hybrid_parallel(fts_mock, "alpha", enable_rerank=False)

    assert rerank_lookup.call_count == 0


# ---------------------------------------------------------------------------
# 7. enable_rerank=True must hand the reranker at most the top 20 merged
#    candidates, even when more were merged.
# ---------------------------------------------------------------------------


def test_cmd_hybrid_parallel_rerank_enabled_applies_top20_only(
    module, monkeypatch
):
    # 25 unique FTS hits → 25 merged candidates → top-20 to the reranker.
    fts_results = [
        _make_search_result(
            module, "global", f"doc{i:02d}.md", snippet=f"s{i}", rank=-float(25 - i)
        )
        for i in range(25)
    ]
    received: dict[str, Any] = {}

    def fake_reranker(query, merged):
        received["query"] = query
        received["merged_len"] = len(merged)
        return merged  # pass-through

    fts_mock, _ = _patch_streams(
        monkeypatch,
        module,
        fts_results=fts_results,
        semantic_results=[],
        bm25_results=None,
        reranker_lookup=lambda: fake_reranker,
    )

    module.cmd_hybrid_parallel(fts_mock, "alpha", enable_rerank=True)

    assert received == {"query": "alpha", "merged_len": 20}


# ---------------------------------------------------------------------------
# 8. CLI `hybrid --parallel --no-rerank <query>` routes to cmd_hybrid_parallel
#    with enable_rerank=False (and cmd_hybrid is NOT called).
# ---------------------------------------------------------------------------


def test_main_hybrid_parallel_flag_parsing_with_no_rerank(module, monkeypatch):
    monkeypatch.setattr(
        sys,
        "argv",
        ["l4_fts5_search.py", "hybrid", "--parallel", "--no-rerank", "alpha", "beta"],
    )

    captured: dict[str, Any] = {}

    def fake_cmd_hybrid_parallel(fts, query, enable_rerank=True):
        captured["query"] = query
        captured["enable_rerank"] = enable_rerank
        captured["fts_cls"] = type(fts).__name__

    def fail_cmd_hybrid(*args, **kwargs):  # noqa: ARG001
        raise AssertionError("cmd_hybrid must not run when --parallel is set")

    monkeypatch.setattr(module, "cmd_hybrid_parallel", fake_cmd_hybrid_parallel)
    monkeypatch.setattr(module, "cmd_hybrid", fail_cmd_hybrid)

    module.main()

    assert captured == {
        "query": "alpha beta",
        "enable_rerank": False,
        "fts_cls": "L4FTS5Search",
    }


# ---------------------------------------------------------------------------
# 9a. Parity guard: cmd_hybrid() and cmd_hybrid_parallel() must produce the
#     same merged ranking and source attribution on identical fake streams
#     (timing-only lines are stripped before comparison). This is the
#     overarching invariant the per-engine tests above enforce piecewise.
# ---------------------------------------------------------------------------


def _strip_timing_and_header(out: str) -> list[str]:
    """Remove timing lines and the parallel/sequential header so the merged
    ranking lines can be compared verbatim between the two code paths.
    """
    skip_prefixes = (
        "[HYBRID SEARCH",  # header line differs by "- PARALLEL" suffix
        "Fetch time:",
        "Merge time:",
        "Rerank time:",
        "Total time:",
    )
    return [
        line
        for line in out.splitlines()
        if line.strip() and not line.startswith(skip_prefixes)
    ]


def test_cmd_hybrid_parity_with_cmd_hybrid_parallel(module, monkeypatch, capsys):
    fts_results = [
        _make_search_result(module, "global", "notes.md", snippet="alpha fts", rank=-1.0),
        _make_search_result(module, "global", "other.md", snippet="beta fts", rank=-0.5),
    ]
    semantic_results = [
        {"key": "[global] notes.md", "text": "alpha sem", "distance": 0.1, "rank": 0},
        {"key": "[global] third.md", "text": "gamma sem", "distance": 0.3, "rank": 1},
    ]
    bm25_results = [
        {"key": "[global] notes.md", "snippet": "alpha bm", "rank": 0, "bm25_score": 1.0}
    ]

    fts_mock, _ = _patch_streams(
        monkeypatch,
        module,
        fts_results=fts_results,
        semantic_results=semantic_results,
        bm25_results=bm25_results,
    )

    module.cmd_hybrid_parallel(fts_mock, "alpha", enable_rerank=False)
    parallel_out = _strip_timing_and_header(capsys.readouterr().out)

    # Reset side-effects on the same fakes (semantic / bm25 are pure
    # closures, fts_mock.search.return_value is unchanged).
    module.cmd_hybrid(fts_mock, "alpha", enable_rerank=False)
    sequential_out = _strip_timing_and_header(capsys.readouterr().out)

    assert parallel_out == sequential_out, (
        "cmd_hybrid_parallel and cmd_hybrid diverged on identical streams:\n"
        f"parallel:\n{parallel_out}\nsequential:\n{sequential_out}"
    )


# ---------------------------------------------------------------------------
# 9. _fetch_semantic_results now runs the semantic engine in-process via
#    _get_semantic_memory() instead of shelling out to a subprocess. It must:
#      - return [] when the engine is unavailable (_get_semantic_memory None);
#      - return [] when the engine's search_all() raises;
#      - otherwise normalise each hit to the documented
#        {key, text, distance, metadata, source} contract, dropping engine
#        internals such as id/_chunks.
# ---------------------------------------------------------------------------


def test_fetch_semantic_results_returns_empty_when_engine_unavailable(
    module, monkeypatch
):
    # _get_semantic_memory() returns None (optional module/engine missing).
    monkeypatch.setattr(module, "_get_semantic_memory", lambda: None)
    assert module._fetch_semantic_results("alpha") == []


def test_fetch_semantic_results_returns_empty_when_search_raises(
    module, monkeypatch
):
    class _BoomMemory:  # pylint: disable=too-few-public-methods
        def search_all(self, query):  # noqa: ARG002
            raise RuntimeError("semantic boom")

    monkeypatch.setattr(module, "_get_semantic_memory", lambda: _BoomMemory())
    assert module._fetch_semantic_results("alpha") == []


def test_fetch_semantic_results_normalizes_hits(module, monkeypatch):
    class _Memory:  # pylint: disable=too-few-public-methods
        def search_all(self, query):  # noqa: ARG002
            return [
                {
                    "id": "chunk-1",
                    "key": "[global] notes.md",
                    "text": "alpha semantic",
                    "distance": 0.12,
                    "metadata": {"source": "global"},
                    "source": "global",
                    "_chunks": ["a", "b"],
                }
            ]

    monkeypatch.setattr(module, "_get_semantic_memory", lambda: _Memory())
    results = module._fetch_semantic_results("alpha")

    assert results == [
        {
            "key": "[global] notes.md",
            "text": "alpha semantic",
            "distance": 0.12,
            "metadata": {"source": "global"},
            "source": "global",
        }
    ]
    # Engine internals must not leak through normalisation.
    assert "id" not in results[0]
    assert "_chunks" not in results[0]


# ---------------------------------------------------------------------------
# 9b. hybrid_search() is the importable counterpart to cmd_hybrid(): it must
#     RETURN the merged ranking (so in-process callers like the MCP server can
#     consume it) rather than print it, and return [] when no engine has a
#     hit.
# ---------------------------------------------------------------------------


def test_hybrid_search_returns_merged_ranking(module, monkeypatch):
    fts_results = [
        _make_search_result(module, "global", "notes.md", snippet="alpha fts", rank=-1.0)
    ]
    semantic_results = [
        {"key": "[global] notes.md", "text": "alpha sem", "distance": 0.1, "rank": 0}
    ]

    fts_mock, _ = _patch_streams(
        monkeypatch,
        module,
        fts_results=fts_results,
        semantic_results=semantic_results,
        bm25_results=None,  # BM25 module unavailable
    )

    merged = module.hybrid_search(fts_mock, "alpha", enable_rerank=False)

    assert len(merged) == 1
    entry = merged[0]
    assert entry.key == make_join_key("global", "notes.md")
    assert set(entry.sources.keys()) == {"fts", "semantic"}


def test_hybrid_search_returns_empty_when_no_engine_has_hits(module, monkeypatch):
    fts_mock, _ = _patch_streams(
        monkeypatch,
        module,
        fts_results=[],
        semantic_results=[],
        bm25_results=None,
    )

    assert module.hybrid_search(fts_mock, "nothing", enable_rerank=False) == []


# ---------------------------------------------------------------------------
# 10. sanitize_fts5_query(): current contract (AUDIT #1 regression lock).
#
#     These pin the *current* behaviour of the FTS5 query sanitiser (the
#     runtime fix from PR #32): every word token is individually wrapped in
#     double quotes (an implicit AND of single-token phrases), punctuation-
#     only input collapses to "", and FTS5 operators / special chars are kept
#     as literal tokens rather than honoured as query syntax. This asserts the
#     *existing* contract, NOT a desired v2 (operators / prefix / phrase).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("C++", '"C"'),
        ("foo:bar", '"foo" "bar"'),
        ('"exact phrase"', '"exact" "phrase"'),
        ("cats OR dogs", '"cats" "OR" "dogs"'),
        ("!!!", ""),
        ("???", ""),
        ("foo*", '"foo"'),
        ("привет мир", '"привет" "мир"'),
        ("", ""),
        ("   ", ""),
    ],
)
def test_sanitize_fts5_query_current_contract(module, raw, expected):
    assert module.sanitize_fts5_query(raw) == expected


def test_sanitize_fts5_query_treats_operators_as_literals_current_contract(module):
    # CURRENT contract: a bare FTS5 operator is quoted into a literal token,
    # i.e. an implicit AND of three single-token phrases, NOT a boolean OR.
    # A future v2 sanitiser that honours OR must update this assertion on
    # purpose — a deliberate contract change, not a broken test.
    assert module.sanitize_fts5_query("cats OR dogs") == '"cats" "OR" "dogs"'


# ---------------------------------------------------------------------------
# 11. Live FTS5: search() over a tmp DB must survive adversarial input and
#     never raise sqlite3.OperationalError. A positive C++ hit and a negative
#     operators-as-literals case make the integration coverage meaningful
#     (they prove the sanitised MATCH actually executes and current operator
#     semantics hold), since the public search() boundary alone is a weak
#     guard while _cached_search_impl still wraps MATCH in a broad except.
#     All tests use tmp_path and disable cost tracking so ~/.claude is never
#     touched.
# ---------------------------------------------------------------------------


def _build_indexed_engine(module, tmp_path, monkeypatch, content):
    """Build an L4FTS5Search over a temp DB and index one small md document.

    Cost tracking is disabled so search() never instantiates CostTracker and
    the test stays fully inside tmp_path (no writes to ~/.claude).
    """
    monkeypatch.setattr(module, "COST_TRACKING_ENABLED", False)
    engine = module.L4FTS5Search(db_path=tmp_path / "fts.db")
    assert engine.init_fts() is True
    doc = tmp_path / "notes.md"
    doc.write_text(content, encoding="utf-8")
    assert engine.index_file(doc, source="global") is True
    return engine


def test_search_special_chars_never_raise_operational_error(
    module, tmp_path, monkeypatch
):
    engine = _build_indexed_engine(
        module, tmp_path, monkeypatch, "Learning C++ and Python. cats and dogs."
    )
    adversarial = [
        "C++",
        "foo:bar",
        '"exact phrase"',
        "cats OR dogs",
        "!!!",
        "???",
        "foo*",
        "привет мир",
    ]
    for query in adversarial:
        try:
            results = engine.search(query, limit=10)
        except sqlite3.OperationalError as exc:  # pragma: no cover
            pytest.fail(f"search({query!r}) raised OperationalError: {exc}")
        assert isinstance(results, list)
        assert all(isinstance(r, module.SearchResult) for r in results)


def test_search_punctuation_only_returns_empty_list(module, tmp_path, monkeypatch):
    engine = _build_indexed_engine(
        module, tmp_path, monkeypatch, "some indexed content here"
    )
    assert engine.search("!!!", limit=10) == []
    assert engine.search("???", limit=10) == []


def test_search_special_char_token_still_matches_document(
    module, tmp_path, monkeypatch
):
    # "C++" sanitises to '"C"'; the unicode61 tokenizer also reduces the
    # indexed "C++" to the token "c", so a real MATCH must succeed and return
    # the document — proving the sanitised query is valid FTS5 and actually
    # executed, not merely swallowed by the broad except.
    engine = _build_indexed_engine(
        module, tmp_path, monkeypatch, "Learning C++ and Python today."
    )
    results = engine.search("C++", limit=10)
    assert len(results) >= 1
    assert results[0].source == "fts5"
    assert results[0].path.startswith("[global]")
    assert results[0].path.endswith("notes.md")


def test_search_treats_fts5_operators_as_literals_current_contract(
    module, tmp_path, monkeypatch
):
    # Integration counterpart to the unit operator test: because OR is a
    # literal token AND-ed with the others, a document containing "cats" and
    # "dogs" but not the literal token "or" yields no hit. This locks the
    # CURRENT operator semantics; a future v2 that honours OR must change this
    # on purpose.
    engine = _build_indexed_engine(
        module, tmp_path, monkeypatch, "cats and dogs are here"
    )
    assert engine.search("cats OR dogs", limit=10) == []


# ---------------------------------------------------------------------------
# 12. _cached_search_impl exception narrowing (AUDIT #5, first slice).
#
#     The cached-search except block was narrowed from a blanket
#     ``except Exception`` to ``except sqlite3.Error``. These tests target
#     that except *directly* by patching the instance's _get_connection so it
#     raises from inside _cached_search_impl (rather than breaking the public
#     search() setup indirectly):
#       - an expected SQLite error degrades gracefully to [] and is logged;
#       - an unexpected non-SQLite error is NOT swallowed and propagates, so
#         real bugs stay visible instead of being masked as an empty result.
#     This is the actual bug class #5 is about — replacing one silent swallow
#     with a narrower one would defeat the point, so both directions are
#     pinned.
# ---------------------------------------------------------------------------


def test_cached_search_degrades_gracefully_on_sqlite_error(
    module, tmp_path, monkeypatch, caplog
):
    engine = module.L4FTS5Search(db_path=tmp_path / "fts.db")

    def boom():
        raise sqlite3.OperationalError("forced sqlite failure")

    # Patch on the instance so _cached_search_impl's `self._get_connection()`
    # raises a SQLite error from within the targeted try/except.
    monkeypatch.setattr(engine, "_get_connection", boom)

    with caplog.at_level(logging.ERROR):
        results = engine.search("alpha", limit=10)

    assert results == []
    assert any(
        "Cached search failed" in rec.getMessage() for rec in caplog.records
    )


def test_cached_search_propagates_unexpected_non_sqlite_error(
    module, tmp_path, monkeypatch
):
    engine = module.L4FTS5Search(db_path=tmp_path / "fts.db")

    def boom():
        raise RuntimeError("unexpected non-sqlite failure")

    # A non-sqlite3.Error raised inside _cached_search_impl must NOT be caught
    # by the narrowed `except sqlite3.Error` block — it must propagate so real
    # bugs stay visible instead of being masked as an empty result.
    monkeypatch.setattr(engine, "_get_connection", boom)

    with pytest.raises(RuntimeError, match="unexpected non-sqlite failure"):
        engine.search("alpha", limit=10)
