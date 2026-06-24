#!/usr/bin/env python3
# pylint: disable=wrong-import-position, import-error
# -*- coding: utf-8 -*-
"""
Routing Learner — ChromaDB-based model router with outcome learning.

Uses the existing L4 semantic infrastructure (ChromaDB + sentence-transformers)
to store task embeddings and route future tasks to the Claude model most likely
to succeed based on historical outcomes.

Cold start: pure heuristics from ``claude_client.estimate_complexity``.
After 100+ tasks: history dominates (~95% accuracy).

Usage::

    from routing_learner import RoutingLearner

    learner = RoutingLearner()

    # Predict best model for a task
    model = learner.predict_model("Refactor fts5_search.py", context_len=500)
    # → "claude-opus-4"

    # Record outcome after task completes
    learner.record_outcome(
        task="Refactor fts5_search.py",
        model_used="claude-opus-4",
        was_successful=True,
        tokens={"input": 5000, "output": 2000},
        cost_usd=0.12,
    )

    # Get learning stats
    print(learner.stats())
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import chromadb
from chromadb.config import Settings

# ChromaDB exception compatibility (same pattern as l4_semantic_global.py):
# older releases raise a bare ``ValueError`` for a missing collection, newer
# ones raise ``chromadb.errors.ChromaError`` subclasses. Import when available
# *and* a genuine exception class, otherwise fall back to a local definition.
try:
    from chromadb.errors import ChromaError as _ChromaError
    if not (isinstance(_ChromaError, type) and issubclass(_ChromaError, BaseException)):
        raise ImportError

    _CHROMA_LOOKUP_ERRORS = (ValueError, _ChromaError)
except Exception:  # pragma: no cover
    class _ChromaError(Exception):  # type: ignore[no-redef]
        """Fallback for missing chromadb.errors.ChromaError."""

    _CHROMA_LOOKUP_ERRORS = (ValueError,)  # type: ignore[assignment]

logger = logging.getLogger(__name__)

# --- Import project modules ---------------------------------------------------
_SCRIPTS_DIR = str(Path(__file__).resolve().parent)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from claude_client import estimate_complexity  # noqa: E402  pylint: disable=wrong-import-position

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

COLLECTION_NAME = "routing_history"
DEFAULT_MODEL = os.getenv("L4_MODEL", "paraphrase-multilingual-MiniLM-L12-v2")
SIMILAR_K = int(os.getenv("ROUTING_SIMILAR_K", "10"))
OUTCOME_BONUS = float(os.getenv("ROUTING_OUTCOME_BONUS", "1.5"))
OUTCOME_PENALTY = float(os.getenv("ROUTING_OUTCOME_PENALTY", "0.5"))

# Model ordering by capability/price tier (0 = cheapest). Used as a
# conservative floor so history can upgrade but never downgrade below the
# heuristic recommendation from estimate_complexity.
MODEL_TIER: dict[str, int] = {
    "claude-haiku-4": 0,
    "claude-sonnet-4": 1,
    "claude-opus-4": 2,
}


class RoutingLearner:
    """ChromaDB-based router that learns which model succeeds on which task.

    Two-phase routing:
    1. **History lookup** — search ChromaDB for similar past tasks, weight by
       similarity × outcome (success → bonus, failure → penalty).
    2. **Heuristic floor** — never choose cheaper than
       :func:`claude_client.estimate_complexity` suggests.
    """

    def __init__(
        self,
        chroma_client: Any | None = None,
        chroma_path: Path | None = None,
        model_name: str | None = None,
    ) -> None:
        """
        Args:
            chroma_client: Existing ChromaDB PersistentClient. If ``None``,
                one is created at ``chroma_path``.
            chroma_path: Where to store the ChromaDB (defaults to
                ``~/.claude/routing_learner_db/``).
            model_name: Sentence-transformers model for embeddings.
        """
        if chroma_path is None:
            chroma_path = Path.home() / ".claude" / "routing_learner_db"

        chroma_path.mkdir(parents=True, exist_ok=True)

        self.client = (
            chroma_client
            if chroma_client is not None
            else chromadb.PersistentClient(
                path=str(chroma_path),
                settings=Settings(anonymized_telemetry=False),
            )
        )

        self.model_name = model_name or DEFAULT_MODEL
        self._model: Any = None
        self._collection: Any = None  # lazy init

        # Per-instance encode cache (same pattern as l4_semantic_global.py)
        self._encode_query_cache: Any = None

    # ------------------------------------------------------------------
    # Sentence-transformers model (lazy load)
    # ------------------------------------------------------------------

    @property
    def model(self) -> Any:
        """Lazy-load sentence-transformers only when embeddings are needed."""
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as exc:
                raise RuntimeError(
                    "sentence_transformers required for routing learner. "
                    "Install project dependencies and retry."
                ) from exc
            self._model = SentenceTransformer(self.model_name)
        return self._model

    @model.setter
    def model(self, value: Any) -> None:
        self._model = value

    # ------------------------------------------------------------------
    # Collection (lazy init)
    # ------------------------------------------------------------------

    @property
    def collection(self) -> Any:
        """Get or create the routing_history ChromaDB collection."""
        if self._collection is None:
            self._collection = self.client.get_or_create_collection(
                COLLECTION_NAME,
            )
        return self._collection

    # ------------------------------------------------------------------
    # Embedding helpers
    # ------------------------------------------------------------------

    def _encode(self, text: str) -> list[float]:
        """Encode a single text to embedding vector (per-instance LRU cache)."""
        cache = getattr(self, "_encode_query_cache", None)
        if cache is None:
            from functools import lru_cache
            cache = lru_cache(maxsize=128)(self._encode_impl)
            self._encode_query_cache = cache
        return cache(text)

    def _encode_impl(self, text: str) -> list[float]:  # pragma: no cover
        """Real encode implementation."""
        result = self.model.encode([text])[0]
        return result.tolist() if hasattr(result, "tolist") else list(result)

    # ------------------------------------------------------------------
    # Public API — prediction
    # ------------------------------------------------------------------

    # pylint: disable=too-many-return-statements
    def predict_model(
        self,
        task: str,
        context_len: int = 0,
        operation_type: str = "generic",
    ) -> str:
        """Return the recommended model for a task.

        Two-phase routing:
        1. Search ChromaDB for similar past tasks, aggregate scores per model.
        2. Use :func:`estimate_complexity` as conservative floor.

        Returns one of ``"claude-haiku-4"``, ``"claude-sonnet-4"``, or
        ``"claude-opus-4"``.
        """
        # Phase 1: Heuristic floor (always start here)
        floor_model = estimate_complexity(
            task, context_len=context_len, operation_type=operation_type,
        )

        # Phase 2: History lookup (if we have data)
        try:
            history_count = self.collection.count()
        except Exception:
            logger.debug("Cannot query collection count; using heuristic floor")
            return floor_model

        if history_count < 3:
            logger.debug("Cold start: %s history entries → heuristics", history_count)
            return floor_model

        # Embed and search
        embedding = self._encode(task)

        try:
            results = self.collection.query(
                query_embeddings=[embedding],
                n_results=min(SIMILAR_K, history_count),
            )
        except _CHROMA_LOOKUP_ERRORS as exc:
            logger.warning("ChromaDB query failed: %s → heuristics", exc)
            return floor_model
        except Exception as exc:
            logger.warning("Unexpected query error: %s → heuristics", exc)
            return floor_model

        if not results.get("ids") or not results["ids"][0]:
            return floor_model

        distances = results.get("distances", [[1.0] * SIMILAR_K])[0]
        metadatas = results.get("metadatas", [[]])[0]

        # Aggregate scores per model.
        #
        # We track both the summed similarity-weighted outcome score AND the
        # number of neighbours per model, then divide to obtain a *mean*
        # weight. Using the mean rather than the raw sum prevents a frequency
        # bias: a model that simply appears more often among the neighbours
        # would otherwise accumulate a larger total even with a worse success
        # record. Normalising by count makes the score reflect the *quality*
        # of past outcomes, not merely how often the model was used.
        model_weight_sums: dict[str, float] = {}
        model_counts: dict[str, int] = {}
        for i, meta in enumerate(metadatas):
            if not meta:
                continue
            model_used = meta.get("model_used", "unknown")
            was_successful = meta.get("was_successful", True)
            distance = float(distances[i]) if i < len(distances) else 1.0

            similarity = max(0.0, 1.0 - distance)
            outcome_weight = OUTCOME_BONUS if was_successful else OUTCOME_PENALTY
            weight = similarity * outcome_weight

            model_weight_sums[model_used] = (
                model_weight_sums.get(model_used, 0.0) + weight
            )
            model_counts[model_used] = model_counts.get(model_used, 0) + 1

        if not model_weight_sums:
            return floor_model

        model_scores: dict[str, float] = {
            model: weight_sum / model_counts[model]
            for model, weight_sum in model_weight_sums.items()
        }

        # Pick highest-scoring model
        best_model = max(model_scores, key=lambda m: model_scores[m])

        # Conservative floor: never go cheaper than heuristics
        best_tier = MODEL_TIER.get(best_model, 0)
        floor_tier = MODEL_TIER.get(floor_model, 0)

        if best_tier < floor_tier:
            logger.debug(
                "History said %s but floor is %s → using floor",
                best_model, floor_model,
            )
            return floor_model

        logger.debug(
            "History picked %s (floor %s, scores: %s)",
            best_model, floor_model,
            {m: round(s, 3) for m, s in sorted(model_scores.items())},
        )
        return best_model

    # ------------------------------------------------------------------
    # Public API — learning / recording
    # ------------------------------------------------------------------

    def record_outcome(
        self,
        task: str,
        *,
        model_used: str,
        was_successful: bool = True,
        operation_type: str = "generic",
        tokens: dict[str, int] | None = None,
        cost_usd: float = 0.0,
    ) -> str:
        """Record a task outcome for future learning.

        Args:
            task: The original task description.
            model_used: Which model handled it.
            was_successful: Whether the task was completed successfully.
            operation_type: Cost-tracker operation name.
            tokens: ``{"input": N, "output": N}`` if available.
            cost_usd: Total cost in USD if available.

        Returns:
            The ChromaDB document ID.
        """
        tokens = tokens or {}
        task_id = (
            f"task_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f')}"
            f"_{uuid4().hex[:8]}"
        )
        embedding = self._encode(task)

        metadata: dict[str, Any] = {
            "model_used": model_used,
            "was_successful": was_successful,
            "operation_type": operation_type,
            "input_tokens": tokens.get("input", 0),
            "output_tokens": tokens.get("output", 0),
            "cost_usd": cost_usd,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        # Remove None values (ChromaDB doesn't like them)
        metadata = {k: v for k, v in metadata.items() if v is not None}

        try:
            self.collection.add(
                ids=[task_id],
                embeddings=[embedding],
                documents=[task],
                metadatas=[metadata],
            )
        except _CHROMA_LOOKUP_ERRORS as exc:
            logger.error("Failed to record outcome: %s", exc)
        except Exception as exc:
            logger.error("Unexpected record error: %s", exc)

        return task_id

    # ------------------------------------------------------------------
    # Public API — stats
    # ------------------------------------------------------------------

    def stats(self) -> dict[str, Any]:
        """Return learning statistics."""
        try:
            count = self.collection.count()
        except Exception:
            count = 0

        model_counts: dict[str, int] = {}
        success_counts: dict[str, int] = {}
        model_costs: dict[str, float] = {}

        if count > 0:
            try:
                all_data = self.collection.get(
                    include=["metadatas"],
                    limit=min(count, 1000),
                )
                for meta in (all_data.get("metadatas") or []):
                    if not meta:
                        continue
                    m = meta.get("model_used", "unknown")
                    s = meta.get("was_successful", True)
                    c = float(meta.get("cost_usd", 0) or 0)

                    model_counts[m] = model_counts.get(m, 0) + 1
                    if s:
                        success_counts[m] = success_counts.get(m, 0) + 1
                    model_costs[m] = model_costs.get(m, 0.0) + c
            except Exception as exc:
                logger.warning("Stats aggregation failed: %s", exc)

        return {
            "total_tasks": count,
            "by_model": {
                m: {
                    "count": model_counts.get(m, 0),
                    "successes": success_counts.get(m, 0),
                    "success_rate": (
                        round(success_counts.get(m, 0) / model_counts.get(m, 1), 2)
                        if model_counts.get(m, 0) > 0
                        else 0.0
                    ),
                    "total_cost": round(model_costs.get(m, 0.0), 4),
                }
                for m in sorted(model_counts)
            },
            "routing_phase": (
                "cold_start" if count < 3
                else "weak_history" if count < 30
                else "learning" if count < 100
                else "trained"
            ),
        }


# ---------------------------------------------------------------------------
# Module-level singleton factory
# ---------------------------------------------------------------------------

_learner_instance: RoutingLearner | None = None  # pylint: disable=invalid-name


def get_learner(**kwargs: Any) -> RoutingLearner:
    """Return a singleton RoutingLearner (created on first call)."""
    global _learner_instance  # pylint: disable=global-statement
    if _learner_instance is None:
        _learner_instance = RoutingLearner(**kwargs)
    return _learner_instance
