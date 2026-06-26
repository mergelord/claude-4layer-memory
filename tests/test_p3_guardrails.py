"""P3 guardrail tests: input clamps, daily budget, routing privacy + pruning."""
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import mcp_server  # noqa: E402  pylint: disable=wrong-import-position
from cost_tracker import CostTracker  # noqa: E402  pylint: disable=wrong-import-position
from routing_learner import RoutingLearner  # noqa: E402  pylint: disable=wrong-import-position


# --------------------------------------------------------------------------
# Input clamps (mcp_server)
# --------------------------------------------------------------------------

def test_clamp_limit_bounds():
    assert mcp_server._clamp_limit(5) == 5
    assert mcp_server._clamp_limit(0) == 1
    assert mcp_server._clamp_limit(-7) == 1
    assert mcp_server._clamp_limit(10 ** 9) == mcp_server.MAX_RESULT_LIMIT
    assert mcp_server._clamp_limit("not-an-int") == 10


def test_clamp_text_trims_and_handles_empty():
    assert mcp_server._clamp_text("hello", 100) == "hello"
    assert mcp_server._clamp_text("x" * 50, 10) == "x" * 10
    assert mcp_server._clamp_text("", 10) == ""
    assert mcp_server._clamp_text(None, 10) == ""


def test_search_memory_clamps_huge_limit(monkeypatch):
    captured = {}

    def fake_search(query, limit):
        captured["args"] = (query, limit)
        return []

    monkeypatch.setattr(mcp_server.fts5_search, "search", fake_search)
    mcp_server.search_memory("hello", limit=10 ** 9)

    assert captured["args"] == ("hello", mcp_server.MAX_RESULT_LIMIT)


# --------------------------------------------------------------------------
# Daily budget guardrail (CostTracker)
# --------------------------------------------------------------------------

def test_budget_disabled_by_default(tmp_path, monkeypatch):
    monkeypatch.delenv("L4_DAILY_BUDGET_USD", raising=False)
    tracker = CostTracker(db_path=tmp_path / "costs.db")

    assert tracker.daily_budget_usd() == 0.0
    status = tracker.budget_status()
    assert status["enabled"] is False
    assert status["exceeded"] is False
    assert status["remaining_usd"] is None


def test_budget_exceeded_detected(tmp_path, monkeypatch):
    monkeypatch.setenv("L4_DAILY_BUDGET_USD", "0.01")
    tracker = CostTracker(db_path=tmp_path / "costs.db")

    # 1,000,000 Opus input tokens @ $15/M = $15 spend, far above the $0.01 cap.
    tracker.track_operation(
        "smart_complete",
        input_tokens=1_000_000,
        model="claude-opus-4",
    )

    assert tracker.get_today_spend() >= 15.0
    status = tracker.budget_status()
    assert status["enabled"] is True
    assert status["exceeded"] is True
    assert status["remaining_usd"] < 0


# --------------------------------------------------------------------------
# Routing learner: privacy + history pruning
# --------------------------------------------------------------------------

class _FakeCollection:
    """In-memory stand-in for a ChromaDB collection."""

    def __init__(self):
        self._store = {}
        self.add_calls = 0
        self.delete_calls = 0

    def count(self):
        return len(self._store)

    def add(self, ids, embeddings, documents, metadatas):
        self.add_calls += 1
        for i, entry_id in enumerate(ids):
            self._store[entry_id] = (embeddings[i], documents[i], metadatas[i])

    def get(self, include=None, limit=None):
        ids = list(self._store.keys())
        return {
            "ids": ids,
            "documents": [self._store[i][1] for i in ids],
            "metadatas": [self._store[i][2] for i in ids],
        }

    def delete(self, ids):
        self.delete_calls += 1
        for entry_id in ids:
            self._store.pop(entry_id, None)


class _FakeModel:
    """Deterministic encoder so no real model download is needed."""

    def encode(self, texts):
        return [[float(len(text)), 1.0, 2.0] for text in texts]


def _make_learner(tmp_path):
    learner = RoutingLearner(chroma_client=object(), chroma_path=tmp_path)
    learner._collection = _FakeCollection()
    learner.model = _FakeModel()
    return learner


def test_record_outcome_stores_raw_task_by_default(tmp_path, monkeypatch):
    monkeypatch.delenv("ROUTING_STORE_TASK_TEXT", raising=False)
    learner = _make_learner(tmp_path)

    learner.record_outcome(task="refactor parser", model_used="claude-sonnet-4")

    assert learner.collection.get()["documents"] == ["refactor parser"]


def test_record_outcome_hashes_task_when_opted_out(tmp_path, monkeypatch):
    monkeypatch.setenv("ROUTING_STORE_TASK_TEXT", "0")
    learner = _make_learner(tmp_path)
    secret = "delete the production database now"

    learner.record_outcome(task=secret, model_used="claude-sonnet-4")

    docs = learner.collection.get()["documents"]
    assert len(docs) == 1
    assert docs[0].startswith("sha256:")
    assert secret not in docs[0]


def test_prune_history_disabled_returns_zero(tmp_path, monkeypatch):
    monkeypatch.delenv("ROUTING_HISTORY_MAX", raising=False)
    learner = _make_learner(tmp_path)
    learner.collection.add(
        ids=["a"],
        embeddings=[[0.0, 0.0, 0.0]],
        documents=["x"],
        metadatas=[{"timestamp": "2026-01-01T00:00:00"}],
    )

    assert learner.prune_history() == 0
    assert learner.collection.count() == 1


def test_prune_history_deletes_oldest(tmp_path):
    learner = _make_learner(tmp_path)
    for n in range(5):
        learner.collection.add(
            ids=[f"task_{n}"],
            embeddings=[[0.0, 0.0, 0.0]],
            documents=[f"task {n}"],
            metadatas=[{"timestamp": f"2026-01-0{n + 1}T00:00:00"}],
        )

    deleted = learner.prune_history(max_entries=2)

    assert deleted == 3
    assert learner.collection.count() == 2
    assert set(learner.collection.get()["ids"]) == {"task_3", "task_4"}
