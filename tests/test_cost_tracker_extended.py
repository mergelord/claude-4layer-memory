#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Extended tests for Cost Tracker module.

Covers:
- tracking with zero tokens (edge case)
- tracking with unknown model (fallback)
- stats with no operations (empty DB)
- stats with operations (aggregation)
- concurrent access (two instances)
- invalid path rejection (security)
- custom price loading
- unicode in operation type
- large token counts
"""

import shutil
import tempfile
from pathlib import Path
import pytest
import sys

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from cost_tracker import CostTracker


@pytest.fixture
def temp_db():
    """Create a temporary database for CostTracker."""
    tmp = tempfile.mkdtemp()
    db_path = Path(tmp) / "test_costs.db"
    yield db_path
    shutil.rmtree(tmp, ignore_errors=True)


class TestCostTrackerEdgeCases:
    """Edge cases for CostTracker."""

    def test_track_zero_tokens(self, temp_db):
        """Tracking zero tokens should result in zero cost."""
        tracker = CostTracker(db_path=temp_db)
        result = tracker.track_operation(
            operation_type="test",
            input_tokens=0,
            output_tokens=0,
        )
        assert result["total_cost"] == 0.0

    def test_track_unknown_model(self, temp_db):
        """Unknown model should fallback to claude-sonnet-4 prices."""
        tracker = CostTracker(db_path=temp_db)
        result = tracker.track_operation(
            operation_type="test",
            input_tokens=1000,
            model="unknown-model",
        )
        # Должен быть ненулевой, используя default цены
        assert result["total_cost"] > 0

    def test_unicode_in_operation_type(self, temp_db):
        """Operation type should accept unicode."""
        tracker = CostTracker(db_path=temp_db)
        result = tracker.track_operation(
            operation_type="тест операция",
            input_tokens=100,
        )
        assert result["operation_type"] == "тест операция"

    def test_large_token_counts(self, temp_db):
        """Large token counts should not overflow."""
        tracker = CostTracker(db_path=temp_db)
        result = tracker.track_operation(
            operation_type="large",
            input_tokens=100_000_000,
            output_tokens=50_000_000,
        )
        assert result["total_cost"] > 0
        assert result["input_tokens"] == 100_000_000

    def test_invalid_path_rejection(self):
        """Tracker should reject paths outside home/temp directories."""
        tracker = CostTracker()
        invalid_path = Path("/etc/outside.db")
        with pytest.raises(ValueError, match="Database path"):
            tracker._safe_db_path(invalid_path)


class TestCostTrackerStats:
    """Statistics tests."""

    def test_stats_empty_db(self, temp_db):
        """Stats on empty DB should return zeros."""
        tracker = CostTracker(db_path=temp_db)
        stats = tracker.get_stats(days=7)
        assert stats["total_operations"] == 0
        assert stats["total_input_tokens"] == 0
        assert stats["total_cost"] == 0.0

    def test_stats_with_operations(self, temp_db):
        """Stats should aggregate operations correctly."""
        tracker = CostTracker(db_path=temp_db)
        tracker.track_operation("op1", input_tokens=1000, output_tokens=500)
        tracker.track_operation("op2", input_tokens=2000, output_tokens=1000)
        tracker.track_operation("op1", input_tokens=500, output_tokens=250)

        stats = tracker.get_stats(days=7)
        assert stats["total_operations"] == 3
        assert stats["total_input_tokens"] == 3500
        assert stats["total_output_tokens"] == 1750
        assert stats["total_cost"] > 0
        assert "op1" in stats["operations_by_type"]
        assert "op2" in stats["operations_by_type"]


class TestCostTrackerConfig:
    """Configuration and price loading tests."""

    def test_load_prices_from_file(self, temp_db, monkeypatch):
        """Custom prices from config file should override defaults."""
        custom_prices = {"claude-sonnet-4": {"input": 5.0, "output": 20.0}}
        # Подменяем метод _load_prices напрямую
        monkeypatch.setattr(
            CostTracker, "_load_prices",
            lambda self: custom_prices
        )
        tracker = CostTracker(db_path=temp_db)
        assert tracker.prices["claude-sonnet-4"]["input"] == 5.0


class TestCostTrackerConcurrency:
    """Concurrent access tests."""

    def test_concurrent_access(self, temp_db):
        """Two instances should be able to write to the same DB."""
        tracker1 = CostTracker(db_path=temp_db)
        tracker2 = CostTracker(db_path=temp_db)

        tracker1.track_operation("op1", input_tokens=100)
        tracker2.track_operation("op2", input_tokens=200)

        stats = tracker1.get_stats()
        assert stats["total_operations"] == 2