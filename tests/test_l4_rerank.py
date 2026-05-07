#!/usr/bin/env python3
# pylint: disable=wrong-import-position, duplicate-code
# -*- coding: utf-8 -*-
"""Tests for l4_rerank module (pure-function version)."""

import copy
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure scripts/ is importable
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from ranking import RankedResult
from l4_rerank import rerank, _best_snippet


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_candidates():
    """Create three sample RankedResult objects."""
    r1 = RankedResult(
        key="doc1",
        score=0.5,
        normalized_score=1.0,
        sources={
            "fts": [
                {"snippet": "aaa bbb", "score": 0.8},
                {"snippet": "ccc ddd", "score": 0.7},
            ],
            "semantic": [
                {"snippet": "semantic good", "distance": 0.1},
            ],
        },
    )
    r2 = RankedResult(
        key="doc2",
        score=0.4,
        normalized_score=0.8,
        sources={
            "fts": [{"snippet": "xxx yyy", "score": 0.9}],
        },
    )
    r3 = RankedResult(
        key="doc3",
        score=0.3,
        normalized_score=0.6,
        sources={
            "bm25": [{"snippet": "111 222", "score": 0.6}],
        },
    )
    return [r1, r2, r3]


@pytest.fixture
def mock_get_model():
    """Mock _get_model to return a fake model with controlled scores."""
    model = MagicMock()
    model.predict.return_value = [2.5, 1.0, 3.0]
    return model


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_rerank_basic(sample_candidates, mock_get_model):
    """Rerank should reorder candidates by cross-encoder relevance."""
    with patch("l4_rerank._get_model", return_value=mock_get_model):
        result = rerank("test query", sample_candidates)

    assert result[0].key == "doc3"
    assert result[1].key == "doc1"
    assert result[2].key == "doc2"
    assert result[0].rerank_score == 3.0
    assert result[1].rerank_score == 2.5
    assert result[2].rerank_score == 1.0

    # Original list must NOT be mutated
    assert sample_candidates[0].rerank_score is None
    assert sample_candidates[1].rerank_score is None


def test_rerank_empty_candidates():
    """Empty list returns empty list."""
    result = rerank("query", [])
    assert result == []


def test_rerank_model_not_loaded(sample_candidates):
    """If model is None, shallow copy of candidates is returned."""
    with patch("l4_rerank._get_model", return_value=None):
        result = rerank("query", sample_candidates)

    assert result == sample_candidates
    assert result is not sample_candidates
    assert sample_candidates[0].rerank_score is None


def test_rerank_score_is_document_level_only(sample_candidates, mock_get_model):
    """rerank_score must be on RankedResult, NOT duplicated inside hits."""
    with patch("l4_rerank._get_model", return_value=mock_get_model):
        result = rerank("query", sample_candidates)

    for r in result:
        assert isinstance(r.rerank_score, float)
        for hits in r.sources.values():
            for h in hits:
                assert "rerank_score" not in h


def test_rerank_sorting(sample_candidates, mock_get_model):
    """Order is strictly descending by rerank_score."""
    with patch("l4_rerank._get_model", return_value=mock_get_model):
        result = rerank("query", sample_candidates)
    scores = [r.rerank_score for r in result]
    assert scores == sorted(scores, reverse=True)


def test_rerank_prediction_failure(sample_candidates):
    """If model.predict raises, return shallow copy of candidates."""
    mock_model = MagicMock()
    mock_model.predict.side_effect = RuntimeError("GPU error")
    with patch("l4_rerank._get_model", return_value=mock_model):
        result = rerank("query", sample_candidates)

    assert result == sample_candidates
    assert result is not sample_candidates


def test_rerank_missing_snippet(sample_candidates, mock_get_model):
    """Empty snippet is used when no hits contain snippet or text."""
    empty_hit = RankedResult(
        key="empty",
        score=0.0,
        normalized_score=0.0,
        sources={"fts": [{"score": 0.5}]},
    )
    with patch("l4_rerank._get_model", return_value=mock_get_model):
        result = rerank("query", [empty_hit])

    assert len(result) == 1
    assert isinstance(result[0].rerank_score, float)


def test_rerank_uses_best_snippet(sample_candidates, mock_get_model):
    """Rerank should select snippet from the best hit among all sources."""
    best = _best_snippet(sample_candidates[0].sources["fts"])
    assert "aaa bbb" in best

    best = _best_snippet(sample_candidates[1].sources["fts"])
    assert "xxx yyy" in best


def test_rerank_preserves_original_fields(sample_candidates, mock_get_model):
    """Reranking should not modify original RankedResult fields."""
    original_keys = [r.key for r in sample_candidates]
    original_scores = [r.score for r in sample_candidates]
    original_norm = [r.normalized_score for r in sample_candidates]
    original_sources = [dict(r.sources) for r in sample_candidates]

    with patch("l4_rerank._get_model", return_value=mock_get_model):
        _ = rerank("query", sample_candidates)

    for i, r in enumerate(sample_candidates):
        assert r.key == original_keys[i]
        assert r.score == original_scores[i]
        assert r.normalized_score == original_norm[i]
        assert r.sources == original_sources[i]


def test_rerank_adds_rerank_score_field(sample_candidates, mock_get_model):
    """rerank_score is attached to the returned RankedResult objects."""
    with patch("l4_rerank._get_model", return_value=mock_get_model):
        result = rerank("query", sample_candidates)

    for r in result:
        assert hasattr(r, "rerank_score")
        assert isinstance(r.rerank_score, float)


# ---------------------------------------------------------------------------
# New tests (pure-function contract + empty hits)
# ---------------------------------------------------------------------------

def test_rerank_is_pure_function(sample_candidates, mock_get_model):
    """Rerank must NOT mutate the original candidates list or its contents."""
    original_copy = copy.deepcopy(sample_candidates)

    with patch("l4_rerank._get_model", return_value=mock_get_model):
        result = rerank("query", sample_candidates)

    assert result is not sample_candidates

    for orig, orig_copy in zip(sample_candidates, original_copy):
        assert orig.key == orig_copy.key
        assert orig.score == orig_copy.score
        assert orig.normalized_score == orig_copy.normalized_score
        assert orig.sources == orig_copy.sources
        assert getattr(orig, "rerank_score", None) == getattr(orig_copy, "rerank_score", None)


def test_rerank_handles_empty_sources(sample_candidates, mock_get_model):
    """Rerank should work with candidates that have empty sources."""
    empty_sources = RankedResult(
        key="empty_sources",
        score=0.0,
        normalized_score=0.0,
        sources={},
    )
    with patch("l4_rerank._get_model", return_value=mock_get_model):
        result = rerank("query", [empty_sources])

    assert len(result) == 1
    assert isinstance(result[0].rerank_score, float)


def test_rerank_handles_empty_hits_list(sample_candidates, mock_get_model):
    """Rerank should work when a source contains an empty list of hits."""
    empty_hits = RankedResult(
        key="empty_hits",
        score=0.0,
        normalized_score=0.0,
        sources={"bm25": []},
    )
    with patch("l4_rerank._get_model", return_value=mock_get_model):
        result = rerank("query", [empty_hits])

    assert len(result) == 1
    assert isinstance(result[0].rerank_score, float)