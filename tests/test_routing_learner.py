#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unit tests for Routing Learner (scripts/routing_learner.py)

Покрытие:
- Инициализация и ленивая загрузка
- Двухфазный роутинг: heuristic floor + history lookup
- Conservative floor (history не может опустить ниже эвристики)
- Outcome weighting (success → bonus, failure → penalty)
- record_outcome: запись в ChromaDB + возврат task_id
- stats(): routing_phase progression (cold_start → weak_history → learning → trained)
- Отказоустойчивость при ошибках ChromaDB

Тесты НЕ загружают SentenceTransformer и НЕ дотрагиваются до реальной
ChromaDB: chroma_client инжектится как mock, а метод ``_encode``
патчится на детерминированный стаб. Это держит тесты быстрыми (<0.1s)
и изолированными от окружения.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Add parent directory to path (same convention as test_cost_tracker.py)
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.routing_learner import (  # noqa: E402
    MODEL_TIER,
    OUTCOME_BONUS,
    OUTCOME_PENALTY,
    RoutingLearner,
)


# ---------------------------------------------------------------------------
# Fakes / helpers
# ---------------------------------------------------------------------------

class FakeCollection:
    """In-memory stand-in for a ChromaDB collection.

    Implements just enough of the ChromaDB collection surface used by
    RoutingLearner (``count``, ``add``, ``query``, ``get``) so tests can
    exercise the real aggregation logic without touching disk or a
    sentence-transformers model.
    """

    def __init__(self) -> None:
        self._store: dict[str, dict] = {}  # id -> {embedding, document, metadata}

    def count(self) -> int:
        return len(self._store)

    def add(self, *, ids, embeddings, documents, metadatas) -> None:  # noqa: ANN001
        for id_, emb, doc, meta in zip(ids, embeddings, documents, metadatas):
            self._store[id_] = {
                "embedding": emb,
                "document": doc,
                "metadata": dict(meta or {}),
            }

    def query(self, *, query_embeddings, n_results):  # noqa: ANN001
        # Deterministic: return stored items in insertion order, with a
        # fixed small distance so similarity = 1 - distance is stable.
        ids_all = list(self._store.keys())[:n_results]
        metas_all = [self._store[i]["metadata"] for i in ids_all]
        # distance 0.2 → similarity 0.8 for every returned neighbour.
        dists_all = [0.2] * len(ids_all)
        return {"ids": [ids_all], "metadatas": [metas_all], "distances": [dists_all]}

    def get(self, *, include, limit):  # noqa: ANN001
        ids_all = list(self._store.keys())[:limit]
        metas_all = [self._store[i]["metadata"] for i in ids_all]
        return {"ids": ids_all, "metadatas": metas_all}


class FailingCollection(FakeCollection):
    """Collection whose ``count``/``query`` always raise."""

    def count(self) -> int:
        raise RuntimeError("collection unavailable (simulated)")

    def query(self, *, query_embeddings, n_results):  # noqa: ANN001
        raise RuntimeError("query unavailable (simulated)")


class AddFailingCollection(FakeCollection):
    """Collection whose ``add`` always raises — for testing error handling."""

    def add(self, *, ids, embeddings, documents, metadatas):  # noqa: ANN001
        raise RuntimeError("add failed (simulated)")


def _make_learner(collection=None) -> RoutingLearner:
    """Build a RoutingLearner with a mock ChromaDB client + stub encoder.

    The sentence-transformers model is never loaded: ``_encode`` is
    monkeypatched by the caller (see fixtures below) to a deterministic
    stub, so no network/heavy deps are touched.
    """
    client = MagicMock()
    # get_or_create_collection must return whatever collection we inject.
    coll = collection if collection is not None else FakeCollection()
    client.get_or_create_collection.return_value = coll
    learner = RoutingLearner(chroma_client=client, chroma_path=Path("/tmp/rl_test_dummy"))
    return learner


@pytest.fixture
def learner(monkeypatch) -> RoutingLearner:
    """A learner backed by an empty in-memory collection.

    ``_encode`` is stubbed to a constant vector so embeddings are cheap
    and deterministic — we are testing routing *logic*, not embedding
    quality.
    """
    lrn = _make_learner()
    monkeypatch.setattr(lrn, "_encode", lambda text: [0.0, 0.0, 0.0])
    return lrn


# ---------------------------------------------------------------------------
# Init / configuration
# ---------------------------------------------------------------------------

class TestRoutingLearnerInit:
    """Initialization & lazy wiring."""

    def test_constants_are_env_configurable_defaults(self):
        """OUTCOME_BONUS/PENALTY default to 1.5/0.5 (documented contract)."""
        assert OUTCOME_BONUS == 1.5
        assert OUTCOME_PENALTY == 0.5
        assert OUTCOME_BONUS > OUTCOME_PENALTY, "success must outweigh failure"

    def test_model_tier_is_monotonic_by_capability(self):
        """Tier ordering: haiku(0) < sonnet(1) < opus(2) — drives the floor."""
        assert MODEL_TIER["claude-haiku-4"] < MODEL_TIER["claude-sonnet-4"]
        assert MODEL_TIER["claude-sonnet-4"] < MODEL_TIER["claude-opus-4"]

    def test_collection_is_lazy(self):
        """ChromaDB collection must not be created until first access."""
        client = MagicMock()
        client.get_or_create_collection.return_value = FakeCollection()
        lrn = RoutingLearner(chroma_client=client, chroma_path=Path("/tmp/rl_init"))
        # Accessing the constructor must NOT have touched the client yet.
        client.get_or_create_collection.assert_not_called()
        _ = lrn.collection  # first access triggers creation
        client.get_or_create_collection.assert_called_once()

    def test_sentence_transformers_model_is_lazy(self, learner):
        """The heavy ST model is never instantiated in these tests."""
        assert learner._model is None  # not loaded yet


# ---------------------------------------------------------------------------
# predict_model — cold start & floor behaviour
# ---------------------------------------------------------------------------

class TestPredictColdStart:
    """Cold-start (<3 history entries) → pure heuristic floor."""

    def test_empty_history_returns_heuristic(self, learner):
        # operation_type='refactor' is in _ALWAYS_ESCALATE → floor is opus,
        # deterministically (no reliance on fragile keyword matching).
        model = learner.predict_model(
            "fix the bug", operation_type="refactor",
        )
        assert model == "claude-opus-4"

    def test_cold_start_with_two_entries_still_uses_floor(
        self, learner, monkeypatch,
    ):
        # Seed exactly 2 entries (below the <3 threshold).
        monkeypatch.setattr(learner, "_encode", lambda t: [0.0])
        learner.record_outcome(task="t", model_used="claude-haiku-4", was_successful=True)
        learner.record_outcome(task="t", model_used="claude-haiku-4", was_successful=True)
        assert learner.collection.count() == 2

        # Even with "successful on haiku" history, cold start must defer to floor.
        model = learner.predict_model("fix the bug", operation_type="refactor")
        assert model == "claude-opus-4"


class TestPredictConservativeFloor:
    """History can upgrade but never downgrade below the heuristic floor."""

    def test_history_cannot_downgrade_below_floor(self, learner):
        """Floor=opus (operation_type=refactor); history favouring haiku
        must NOT win — the floor overrides a cheaper history pick."""
        for _ in range(5):
            learner.record_outcome(
                task="fix the bug", model_used="claude-haiku-4", was_successful=True,
            )
        assert learner.collection.count() >= 3
        model = learner.predict_model("fix the bug", operation_type="refactor")
        assert model == "claude-opus-4", "floor must override a cheaper history pick"

    def test_history_can_upgrade_above_floor(self, learner):
        """Floor=sonnet (context_len=50000) but history reliably succeeds
        on opus → opus is the history pick and is >= floor tier, so it is
        returned. Uses context_len for a deterministic sonnet floor."""
        for _ in range(5):
            learner.record_outcome(
                task="cache design", model_used="claude-opus-4",
                was_successful=True,
            )
        # context_len=50000 deterministically yields a sonnet floor.
        floor = _heuristic_floor("cache design", context_len=50000)
        assert floor == "claude-sonnet-4", "test precondition: floor must be sonnet"
        model = learner.predict_model("cache design", context_len=50000)
        assert model == "claude-opus-4", (
            "history upgrade to opus (>= sonnet floor) must be honoured"
        )


# ---------------------------------------------------------------------------
# predict_model — outcome weighting (success vs failure)
# ---------------------------------------------------------------------------

class TestOutcomeWeighting:
    """success → OUTCOME_BONUS, failure → OUTCOME_PENALTY."""

    def test_failed_outcome_recorded_with_penalty_metadata(self, learner):
        learner.record_outcome(
            task="t", model_used="claude-opus-4", was_successful=False,
        )
        stored = next(iter(learner.collection._store.values()))
        assert stored["metadata"]["was_successful"] is False

    def test_successful_outcome_recorded_with_success_metadata(self, learner):
        learner.record_outcome(
            task="t", model_used="claude-haiku-4", was_successful=True,
        )
        stored = next(iter(learner.collection._store.values()))
        assert stored["metadata"]["was_successful"] is True

    def test_bonus_greater_than_penalty_drives_success_preference(self):
        """A success must contribute more weight than a failure at equal
        similarity, so the router prefers models with a success track record."""
        # Same similarity (distance 0.2 → sim 0.8) for both; only the
        # outcome weight differs. This is the invariant that makes outcome
        # learning meaningful.
        sim = 0.8
        success_weight = sim * OUTCOME_BONUS
        failure_weight = sim * OUTCOME_PENALTY
        assert success_weight > failure_weight


# ---------------------------------------------------------------------------
# record_outcome — persistence contract
# ---------------------------------------------------------------------------

class TestRecordOutcome:
    """record_outcome writes to the collection and returns a usable id."""

    def test_returns_task_id_with_prefix(self, learner):
        task_id = learner.record_outcome(
            task="do something", model_used="claude-sonnet-4", was_successful=True,
        )
        assert isinstance(task_id, str)
        assert task_id.startswith("task_")

    def test_record_increments_count(self, learner):
        assert learner.collection.count() == 0
        learner.record_outcome(task="t1", model_used="claude-haiku-4")
        learner.record_outcome(task="t2", model_used="claude-sonnet-4")
        assert learner.collection.count() == 2

    def test_record_stores_metadata_fields(self, learner):
        learner.record_outcome(
            task="important task",
            model_used="claude-opus-4",
            was_successful=True,
            tokens={"input": 5000, "output": 2000},
            cost_usd=0.12,
        )
        stored = next(iter(learner.collection._store.values()))
        meta = stored["metadata"]
        assert meta["model_used"] == "claude-opus-4"
        assert meta["was_successful"] is True
        assert meta["input_tokens"] == 5000
        assert meta["output_tokens"] == 2000
        assert meta["cost_usd"] == pytest.approx(0.12)

    def test_record_swallows_collection_error_and_still_returns_id(self):
        """If the collection .add() fails, record_outcome must not raise;
        it logs and still returns the generated id (robustness contract)."""
        lrn = _make_learner(collection=AddFailingCollection())
        lrn._encode = lambda t: [0.0]  # noqa: E731
        task_id = lrn.record_outcome(task="t", model_used="claude-haiku-4")
        assert task_id.startswith("task_")
        assert lrn.collection.count() == 0

    def test_record_outcome_generates_unique_ids(self, learner):
        """UUID suffix ensures no collision even for fast consecutive calls."""
        id1 = learner.record_outcome(task="t", model_used="claude-haiku-4")
        id2 = learner.record_outcome(task="t", model_used="claude-haiku-4")
        assert id1 != id2
        assert learner.collection.count() == 2


# ---------------------------------------------------------------------------
# behavioural — outcome weighting affects predict_model
# ---------------------------------------------------------------------------

class TestBehaviouralOutcomeWeighting:
    """End-to-end: success/failure history influences model selection."""

    def test_success_history_prefers_model_over_failure(self):
        """Outcome weighting must drive predict_model on the history path.

        This is a *real* end-to-end check of outcome weighting, unlike the
        earlier version which seeded only 2 entries and therefore never
        reached the history path (predict_model returns the cold-start
        floor while ``history_count < 3``) — it passed because of the
        floor, not because of any weighting.

        Setup that isolates outcome weighting as the ONLY differentiator:
        - 6 neighbours (>= 3 threshold → history path is active).
        - Every neighbour has identical similarity (FakeCollection returns
          distance 0.2 for all), so similarity cannot decide.
        - Equal counts per model (3 vs 3), so frequency cannot decide.
        - Floor is haiku ("cache design", no escalation, score 0), the
          lowest tier, so the conservative floor cannot override either
          candidate.
        Sonnet has a success track record (OUTCOME_BONUS) while opus only
        failed (OUTCOME_PENALTY); predict_model must therefore pick sonnet
        — even though opus is the higher tier — proving the choice is
        driven by outcomes.
        """
        coll = FakeCollection()
        coll.add(
            ids=["s1", "s2", "s3", "o1", "o2", "o3"],
            embeddings=[[0.0]] * 6,
            documents=["cache design"] * 6,
            metadatas=[
                {"model_used": "claude-sonnet-4", "was_successful": True},
                {"model_used": "claude-sonnet-4", "was_successful": True},
                {"model_used": "claude-sonnet-4", "was_successful": True},
                {"model_used": "claude-opus-4", "was_successful": False},
                {"model_used": "claude-opus-4", "was_successful": False},
                {"model_used": "claude-opus-4", "was_successful": False},
            ],
        )
        lrn = _make_learner(collection=coll)
        lrn._encode = lambda t: [0.0]  # noqa: E731

        # Preconditions that make this an honest test of weighting:
        assert coll.count() == 6, "must be >= 3 so the history path is active"
        assert _heuristic_floor("cache design") == "claude-haiku-4", (
            "floor must be the lowest tier so it cannot override the pick"
        )

        model = lrn.predict_model("cache design")
        assert model == "claude-sonnet-4", (
            "success-weighted sonnet must beat failure-weighted opus"
        )

    def test_failure_history_demotes_model_below_successful_peer(self):
        """Mirror image: with equal counts and similarity, the model that
        succeeded outranks the one that failed even when the failing model
        shares the lower tier. opus(success) must beat sonnet(failure)."""
        coll = FakeCollection()
        coll.add(
            ids=["o1", "o2", "o3", "s1", "s2", "s3"],
            embeddings=[[0.0]] * 6,
            documents=["cache design"] * 6,
            metadatas=[
                {"model_used": "claude-opus-4", "was_successful": True},
                {"model_used": "claude-opus-4", "was_successful": True},
                {"model_used": "claude-opus-4", "was_successful": True},
                {"model_used": "claude-sonnet-4", "was_successful": False},
                {"model_used": "claude-sonnet-4", "was_successful": False},
                {"model_used": "claude-sonnet-4", "was_successful": False},
            ],
        )
        lrn = _make_learner(collection=coll)
        lrn._encode = lambda t: [0.0]  # noqa: E731
        assert _heuristic_floor("cache design") == "claude-haiku-4"
        model = lrn.predict_model("cache design")
        assert model == "claude-opus-4"

    def test_outcome_quality_beats_frequency(self):
        """Frequency must not dominate outcomes: a frequently-failing model
        must lose to a rarely-but-successfully used one.

        haiku appears 5× but always failed; sonnet appears 2× but always
        succeeded. With score normalised by neighbour count, sonnet's mean
        weight (sim*BONUS) beats haiku's (sim*PENALTY) despite haiku's
        higher raw frequency. Floor is haiku, so it cannot override the
        sonnet pick.
        """
        coll = FakeCollection()
        coll.add(
            ids=["h1", "h2", "h3", "h4", "h5", "s1", "s2"],
            embeddings=[[0.0]] * 7,
            documents=["cache design"] * 7,
            metadatas=[
                {"model_used": "claude-haiku-4", "was_successful": False},
                {"model_used": "claude-haiku-4", "was_successful": False},
                {"model_used": "claude-haiku-4", "was_successful": False},
                {"model_used": "claude-haiku-4", "was_successful": False},
                {"model_used": "claude-haiku-4", "was_successful": False},
                {"model_used": "claude-sonnet-4", "was_successful": True},
                {"model_used": "claude-sonnet-4", "was_successful": True},
            ],
        )
        lrn = _make_learner(collection=coll)
        lrn._encode = lambda t: [0.0]  # noqa: E731
        assert _heuristic_floor("cache design") == "claude-haiku-4"
        model = lrn.predict_model("cache design")
        assert model == "claude-sonnet-4", (
            "normalised outcome quality must beat raw frequency"
        )


# ---------------------------------------------------------------------------
# stats — routing_phase progression
# ---------------------------------------------------------------------------

class TestStats:
    """stats() reports routing_phase by entry count."""

    def test_empty_stats_is_cold_start(self, learner):
        s = learner.stats()
        assert s["total_tasks"] == 0
        assert s["routing_phase"] == "cold_start"
        assert s["by_model"] == {}

    def test_phase_progression_thresholds(self, learner):
        # Thresholds (routing_learner.py): cold_start <3, weak_history
        # <30, learning <100, trained >=100.
        learner._encode = lambda t: [0.0]  # noqa: E731

        # 2 entries → cold_start (<3)
        learner.record_outcome(task="t", model_used="claude-haiku-4")
        learner.record_outcome(task="t", model_used="claude-haiku-4")
        assert learner.collection.count() == 2
        assert learner.stats()["routing_phase"] == "cold_start"

        # +1 = 3 entries → weak_history (>=3, <30)
        learner.record_outcome(task="t", model_used="claude-haiku-4")
        assert learner.collection.count() == 3
        assert learner.stats()["routing_phase"] == "weak_history"

        # +27 = 30 entries → learning (>=30, <100)
        for _ in range(27):
            learner.record_outcome(task="t", model_used="claude-sonnet-4")
        assert learner.collection.count() == 30
        assert learner.stats()["routing_phase"] == "learning"

        # +70 = 100 entries → trained (>=100)
        for _ in range(70):
            learner.record_outcome(task="t", model_used="claude-opus-4")
        assert learner.collection.count() == 100
        assert learner.stats()["routing_phase"] == "trained"

    def test_stats_aggregates_per_model(self, learner):
        learner._encode = lambda t: [0.0]  # noqa: E731
        learner.record_outcome(task="t", model_used="claude-haiku-4", was_successful=True)
        learner.record_outcome(task="t", model_used="claude-haiku-4", was_successful=False)
        learner.record_outcome(task="t", model_used="claude-sonnet-4", was_successful=True)
        s = learner.stats()
        assert s["by_model"]["claude-haiku-4"]["count"] == 2
        assert s["by_model"]["claude-haiku-4"]["successes"] == 1
        assert s["by_model"]["claude-sonnet-4"]["count"] == 1
        assert s["by_model"]["claude-sonnet-4"]["successes"] == 1


# ---------------------------------------------------------------------------
# Fault tolerance
# ---------------------------------------------------------------------------

class TestFaultTolerance:
    """Routing degrades to the heuristic floor when ChromaDB is unavailable."""

    def test_predict_falls_back_when_count_fails(self, monkeypatch):
        lrn = _make_learner(collection=FailingCollection())
        monkeypatch.setattr(lrn, "_encode", lambda t: [0.0])
        # count() raises → must not propagate; returns heuristic floor.
        # operation_type=refactor → deterministic opus floor.
        model = lrn.predict_model("fix the bug", operation_type="refactor")
        assert model == "claude-opus-4"

    def test_predict_falls_back_when_query_fails_with_history(self, monkeypatch):
        """count() succeeds (>=3) but query() raises → still returns floor."""
        coll = FakeCollection()
        # Pre-seed so count() >= 3, then swap query to fail.
        coll.add(
            ids=["a", "b", "c"],
            embeddings=[[0.0], [0.0], [0.0]],
            documents=["t", "t", "t"],
            metadatas=[{"model_used": "claude-haiku-4", "was_successful": True}] * 3,
        )
        lrn = _make_learner(collection=coll)
        monkeypatch.setattr(lrn, "_encode", lambda t: [0.0])
        original_query = coll.query
        coll.query = MagicMock(side_effect=RuntimeError("boom"))
        try:
            model = lrn.predict_model("fix the bug", operation_type="refactor")
            assert model == "claude-opus-4"
        finally:
            coll.query = original_query  # restore for fixture cleanliness


# ---------------------------------------------------------------------------
# Private helper (mirrors estimate_complexity for precondition assertions)
# ---------------------------------------------------------------------------

def _heuristic_floor(task: str, context_len: int = 0) -> str:
    """Re-import-free shortcut to the real estimate_complexity floor."""
    from scripts.claude_client import estimate_complexity
    return estimate_complexity(task, context_len=context_len)
