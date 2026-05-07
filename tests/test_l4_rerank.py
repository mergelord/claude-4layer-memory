#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit tests for :mod:`scripts.l4_rerank` (cross-encoder reranking).

Covers:
- Basic reranking functionality
- Empty candidates handling
- Model not loaded graceful degradation
- rerank_score added to sources metadata
- Sorting by rerank_score
- Integration with RankedResult dataclass
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Local package
_SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from ranking import RankedResult  # noqa: E402  pylint: disable=wrong-import-position


# ---------------------------------------------------------------------------
# Basic functionality
# ---------------------------------------------------------------------------


def test_rerank_basic():
    """Rerank should reorder candidates by cross-encoder relevance."""
    with patch("l4_rerank._model") as mock_model:
        mock_model.predict.return_value = [6.5, -2.3, 4.1]

        from l4_rerank import rerank  # noqa: E402

        candidates = [
            RankedResult(
                key="doc1.md",
                score=0.5,
                sources={"fts": [{"snippet": "memory system architecture"}]},
            ),
            RankedResult(
                key="doc2.md",
                score=0.3,
                sources={"fts": [{"snippet": "unrelated content"}]},
            ),
            RankedResult(
                key="doc3.md",
                score=0.4,
                sources={"fts": [{"snippet": "memory management"}]},
            ),
        ]

        reranked = rerank("memory system", candidates)

        # Should be sorted by rerank_score descending
        assert reranked[0].key == "doc1.md"
        assert reranked[0].rerank_score == pytest.approx(6.5)
        assert reranked[1].key == "doc3.md"
        assert reranked[1].rerank_score == pytest.approx(4.1)
        assert reranked[2].key == "doc2.md"
        assert reranked[2].rerank_score == pytest.approx(-2.3)


def test_rerank_empty_candidates():
    """Empty candidate list should return empty list without error."""
    from l4_rerank import rerank  # noqa: E402

    result = rerank("query", [])
    assert result == []


def test_rerank_model_not_loaded():
    """If model is None, should return candidates unchanged."""
    with patch("l4_rerank._model", None):
        from l4_rerank import rerank  # noqa: E402

        candidates = [
            RankedResult(
                key="doc1.md", score=0.5, sources={"fts": [{"snippet": "text"}]}
            ),
            RankedResult(
                key="doc2.md", score=0.3, sources={"fts": [{"snippet": "text"}]}
            ),
        ]

        reranked = rerank("query", candidates)

        # Should return same list, same order
        assert len(reranked) == 2
        assert reranked[0].key == "doc1.md"
        assert reranked[1].key == "doc2.md"
        assert not hasattr(reranked[0], "rerank_score") or reranked[0].rerank_score is None


def test_rerank_score_added_to_sources():
    """rerank_score should be added to each hit in sources metadata."""
    with patch("l4_rerank._model") as mock_model:
        mock_model.predict.return_value = [8.2]

        from l4_rerank import rerank  # noqa: E402

        candidates = [
            RankedResult(
                key="doc.md",
                score=0.5,
                sources={
                    "fts": [{"snippet": "text", "rank": 1}],
                    "semantic": [{"snippet": "text", "distance": 0.2}],
                },
            )
        ]

        reranked = rerank("query", candidates)

        # Check rerank_score added to all sources
        assert reranked[0].sources["fts"][0]["rerank_score"] == pytest.approx(8.2)
        assert reranked[0].sources["semantic"][0]["rerank_score"] == pytest.approx(8.2)


def test_rerank_sorting():
    """Candidates should be sorted by rerank_score descending."""
    with patch("l4_rerank._model") as mock_model:
        # Reverse order scores
        mock_model.predict.return_value = [1.0, 5.0, 3.0]

        from l4_rerank import rerank  # noqa: E402

        candidates = [
            RankedResult(key="a.md", score=0.9, sources={"fts": [{"snippet": "a"}]}),
            RankedResult(key="b.md", score=0.8, sources={"fts": [{"snippet": "b"}]}),
            RankedResult(key="c.md", score=0.7, sources={"fts": [{"snippet": "c"}]}),
        ]

        reranked = rerank("query", candidates)

        # Should be sorted by rerank_score, not original score
        assert reranked[0].key == "b.md"  # rerank_score=5.0
        assert reranked[1].key == "c.md"  # rerank_score=3.0
        assert reranked[2].key == "a.md"  # rerank_score=1.0


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_rerank_prediction_failure():
    """If model.predict raises, should return candidates unchanged."""
    with patch("l4_rerank._model") as mock_model:
        mock_model.predict.side_effect = RuntimeError("Model error")

        from l4_rerank import rerank  # noqa: E402

        candidates = [
            RankedResult(key="doc.md", score=0.5, sources={"fts": [{"snippet": "text"}]})
        ]

        reranked = rerank("query", candidates)

        # Should return original list
        assert len(reranked) == 1
        assert reranked[0].key == "doc.md"


def test_rerank_missing_snippet():
    """If snippet is missing, should use empty string for prediction."""
    with patch("l4_rerank._model") as mock_model:
        mock_model.predict.return_value = [2.0]

        from l4_rerank import rerank  # noqa: E402

        candidates = [
            RankedResult(
                key="doc.md",
                score=0.5,
                sources={"fts": [{"rank": 1}]},  # No snippet
            )
        ]

        reranked = rerank("query", candidates)

        # Should not crash, should call predict with empty string
        mock_model.predict.assert_called_once()
        call_args = mock_model.predict.call_args[0][0]
        assert call_args[0][1] == ""  # (query, text) pair


def test_rerank_multiple_sources_uses_first_snippet():
    """When multiple sources exist, should use snippet from first source."""
    with patch("l4_rerank._model") as mock_model:
        mock_model.predict.return_value = [3.0]

        from l4_rerank import rerank  # noqa: E402

        candidates = [
            RankedResult(
                key="doc.md",
                score=0.5,
                sources={
                    "fts": [{"snippet": "first snippet"}],
                    "semantic": [{"snippet": "second snippet"}],
                },
            )
        ]

        reranked = rerank("query", candidates)

        # Should use first source's snippet
        call_args = mock_model.predict.call_args[0][0]
        assert call_args[0][1] == "first snippet"


# ---------------------------------------------------------------------------
# Integration with RankedResult
# ---------------------------------------------------------------------------


def test_rerank_preserves_original_fields():
    """Reranking should not modify original RankedResult fields."""
    with patch("l4_rerank._model") as mock_model:
        mock_model.predict.return_value = [7.5]

        from l4_rerank import rerank  # noqa: E402

        candidates = [
            RankedResult(
                key="doc.md",
                score=0.42,
                normalized_score=0.85,
                sources={"fts": [{"snippet": "text", "rank": 3}]},
            )
        ]

        reranked = rerank("query", candidates)

        # Original fields should be preserved
        assert reranked[0].key == "doc.md"
        assert reranked[0].score == pytest.approx(0.42)
        assert reranked[0].normalized_score == pytest.approx(0.85)
        assert reranked[0].sources["fts"][0]["rank"] == 3


def test_rerank_adds_rerank_score_field():
    """rerank_score should be added as a new field to RankedResult."""
    with patch("l4_rerank._model") as mock_model:
        mock_model.predict.return_value = [9.1]

        from l4_rerank import rerank  # noqa: E402

        candidates = [
            RankedResult(key="doc.md", score=0.5, sources={"fts": [{"snippet": "text"}]})
        ]

        reranked = rerank("query", candidates)

        assert hasattr(reranked[0], "rerank_score")
        assert reranked[0].rerank_score == pytest.approx(9.1)
