#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit tests for :mod:`scripts.ranking` (RRF merge + normalisation).

Covers:
- Basic correctness (single source, two sources, overlap, no overlap).
- Determinism (stable tie-break by key).
- Multi-hit handling (same key from same source twice → list, not overwrite).
- Edge cases (empty input, all-zero scores, k validation, missing 'key').
- :func:`normalize_scores` mathematical contract.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Local package — keep the sys.path nudge consistent with sibling tests.
_SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from ranking import (  # noqa: E402  pylint: disable=wrong-import-position
    DEFAULT_K,
    RankedResult,
    normalize_scores,
    rrf_merge,
)


# ---------------------------------------------------------------------------
# Basic correctness
# ---------------------------------------------------------------------------


def test_single_source_preserves_order():
    """One stream alone should produce results in input order."""
    fts = [
        {"key": "alpha.md", "snippet": "first"},
        {"key": "beta.md", "snippet": "second"},
        {"key": "gamma.md", "snippet": "third"},
    ]
    merged = rrf_merge(("fts", fts))

    assert [r.key for r in merged] == ["alpha.md", "beta.md", "gamma.md"]
    # Score must strictly decrease since ranks are unique.
    scores = [r.score for r in merged]
    assert scores == sorted(scores, reverse=True)
    assert scores[0] > scores[-1]


def test_two_sources_with_full_overlap():
    """Same keys in both streams → scores combine, top-1 dominates."""
    fts = [{"key": "a.md"}, {"key": "b.md"}]
    sem = [{"key": "a.md"}, {"key": "b.md"}]

    merged = rrf_merge(("fts", fts), ("semantic", sem))

    assert len(merged) == 2
    assert merged[0].key == "a.md"
    # a.md gets rank 1 from both streams, b.md gets rank 2 from both.
    expected_a = 2 * (1.0 / (DEFAULT_K + 1))
    expected_b = 2 * (1.0 / (DEFAULT_K + 2))
    assert merged[0].score == pytest.approx(expected_a)
    assert merged[1].score == pytest.approx(expected_b)


def test_two_sources_with_no_overlap():
    """Disjoint streams → all results retained, sorted by RRF rank-1 score."""
    fts = [{"key": "x.md"}]
    sem = [{"key": "y.md"}]

    merged = rrf_merge(("fts", fts), ("semantic", sem))

    assert len(merged) == 2
    # Both at rank 1 → same RRF score → tie-break by key.
    assert merged[0].key == "x.md"
    assert merged[1].key == "y.md"
    assert merged[0].score == pytest.approx(merged[1].score)


def test_partial_overlap_promotes_overlapping_key():
    """Key in both streams should outrank keys present in only one."""
    fts = [{"key": "shared.md"}, {"key": "fts_only.md"}]
    sem = [{"key": "sem_only.md"}, {"key": "shared.md"}]

    merged = rrf_merge(("fts", fts), ("semantic", sem))

    assert merged[0].key == "shared.md"
    assert merged[0].score > merged[1].score


# ---------------------------------------------------------------------------
# Determinism — flaky-test prevention (Stability test from the design review)
# ---------------------------------------------------------------------------


def test_stable_ordering_reproduces_across_runs():
    """Same input must produce identical output across repeated calls."""
    fts = [{"key": "a.md"}, {"key": "b.md"}, {"key": "c.md"}]
    sem = [{"key": "c.md"}, {"key": "a.md"}, {"key": "b.md"}]

    run1 = rrf_merge(("fts", fts), ("semantic", sem))
    run2 = rrf_merge(("fts", fts), ("semantic", sem))

    assert [r.key for r in run1] == [r.key for r in run2]
    assert [r.score for r in run1] == [r.score for r in run2]


def test_tied_scores_break_by_lexicographic_key():
    """When two keys have identical RRF score, sort by key ascending."""
    # Both at rank 1 in their respective streams → identical RRF score.
    fts = [{"key": "zebra.md"}]
    sem = [{"key": "alpha.md"}]

    merged = rrf_merge(("fts", fts), ("semantic", sem))

    assert merged[0].key == "alpha.md"
    assert merged[1].key == "zebra.md"


# ---------------------------------------------------------------------------
# Multi-hit handling — sources stored as list, never overwritten
# ---------------------------------------------------------------------------


def test_same_key_twice_in_one_source_records_both_hits():
    """If the same key appears at multiple ranks in one source, keep both."""
    fts = [
        {"key": "handoff.md", "snippet": "chunk 1", "bm25": 0.9},
        {"key": "decisions.md", "snippet": "other"},
        {"key": "handoff.md", "snippet": "chunk 2", "bm25": 0.5},
    ]

    merged = rrf_merge(("fts", fts))
    handoff = next(r for r in merged if r.key == "handoff.md")

    assert len(handoff.sources["fts"]) == 2
    snippets = [hit["snippet"] for hit in handoff.sources["fts"]]
    assert "chunk 1" in snippets
    assert "chunk 2" in snippets
    # Both contributions should be summed into total score.
    expected = 1.0 / (DEFAULT_K + 1) + 1.0 / (DEFAULT_K + 3)
    assert handoff.score == pytest.approx(expected)


def test_per_source_payload_excludes_key_includes_rank_and_contribution():
    """Each per-source hit records original metadata + rank + RRF contribution."""
    fts = [{"key": "a.md", "snippet": "hi", "bm25": 0.7}]
    merged = rrf_merge(("fts", fts))

    payload = merged[0].sources["fts"][0]
    assert "key" not in payload  # promoted to top-level RankedResult
    assert payload["snippet"] == "hi"
    assert payload["bm25"] == 0.7
    assert payload["rank"] == 1
    assert payload["rrf_contribution"] == pytest.approx(1.0 / (DEFAULT_K + 1))


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_empty_streams_produce_empty_result():
    """Both streams empty → empty list, no exception."""
    assert rrf_merge(("fts", []), ("semantic", [])) == []


def test_one_empty_stream_falls_back_to_other():
    """Empty FTS + non-empty semantic should rank semantic-only correctly."""
    sem = [{"key": "only.md"}]
    merged = rrf_merge(("fts", []), ("semantic", sem))

    assert len(merged) == 1
    assert merged[0].key == "only.md"
    assert merged[0].score == pytest.approx(1.0 / (DEFAULT_K + 1))


def test_negative_k_raises():
    """Defensive: negative k makes no mathematical sense for RRF."""
    with pytest.raises(ValueError, match="non-negative"):
        rrf_merge(("fts", [{"key": "a.md"}]), k=-1)


def test_missing_key_in_item_raises():
    """A stream item without 'key' is a programming error — fail loud."""
    with pytest.raises(ValueError, match="missing required 'key' field"):
        rrf_merge(("fts", [{"snippet": "no key here"}]))


def test_three_sources_extensible():
    """API is variadic — three streams should merge without changes."""
    a = [{"key": "doc.md"}]
    b = [{"key": "doc.md"}]
    c = [{"key": "doc.md"}]
    merged = rrf_merge(("a", a), ("b", b), ("c", c))

    assert len(merged) == 1
    assert set(merged[0].sources.keys()) == {"a", "b", "c"}
    assert merged[0].score == pytest.approx(3.0 / (DEFAULT_K + 1))


# ---------------------------------------------------------------------------
# normalize_scores
# ---------------------------------------------------------------------------


def test_normalize_scores_top_result_is_one():
    """Top hit's normalized_score must be exactly 1.0."""
    fts = [{"key": "a.md"}, {"key": "b.md"}]
    merged = normalize_scores(rrf_merge(("fts", fts)))

    assert merged[0].normalized_score == pytest.approx(1.0)
    assert 0.0 < merged[1].normalized_score < 1.0


def test_normalize_scores_empty_list_no_error():
    """Empty input must not crash."""
    assert normalize_scores([]) == []


def test_normalize_scores_all_zero_max_assigns_zero_to_all():
    """Edge case: if every score is 0.0, no division by zero."""
    results = [RankedResult(key="a"), RankedResult(key="b")]
    out = normalize_scores(results)

    assert all(r.normalized_score == 0.0 for r in out)


def test_normalize_scores_returns_same_list_for_chaining():
    """Mutates in place and returns the same list (caller convenience)."""
    fts = [{"key": "a.md"}]
    merged = rrf_merge(("fts", fts))
    out = normalize_scores(merged)

    assert out is merged


def test_normalize_scores_preserves_ordering():
    """Normalization must not reorder results."""
    fts = [{"key": "a.md"}, {"key": "b.md"}, {"key": "c.md"}]
    merged = rrf_merge(("fts", fts))
    keys_before = [r.key for r in merged]
    normalize_scores(merged)
    keys_after = [r.key for r in merged]

    assert keys_before == keys_after
