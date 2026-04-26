#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unit tests for Cost Tracker

Покрытие:
- Инициализация и конфигурация
- Отслеживание операций
- Статистика
- Безопасность (валидация путей, проверка прав)
- Загрузка цен из конфига
"""

import json
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.cost_tracker import CostTracker


class TestCostTrackerInit:
    """Test initialization"""

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory"""
        temp_dir = Path(tempfile.mkdtemp())
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_init_default_path(self):
        """Test initialization with default path"""
        tracker = CostTracker()
        assert tracker.db_path.exists()
        assert tracker.db_path.name == "memory_costs.db"

    def test_init_custom_path(self, temp_dir):
        """Test initialization with custom path"""
        db_path = temp_dir / "custom.db"
        tracker = CostTracker(db_path)
        assert tracker.db_path == db_path.resolve()

    def test_safe_db_path_valid(self, temp_dir):
        """Test safe_db_path with valid path"""
        tracker = CostTracker()
        valid_path = Path.home() / "test.db"
        result = tracker._safe_db_path(valid_path)
        assert result.is_absolute()

    def test_safe_db_path_invalid(self):
        """Test safe_db_path rejects path outside home and temp roots"""
        tracker = CostTracker()
        # /etc is outside both Path.home() and tempfile.gettempdir()
        invalid_path = Path("/etc/outside.db")
        with pytest.raises(ValueError, match="Database path"):
            tracker._safe_db_path(invalid_path)

    def test_load_prices_default(self, temp_dir):
        """Test loading default prices when config missing"""
        db_path = temp_dir / "test.db"
        tracker = CostTracker(db_path)
        assert 'claude-sonnet-4' in tracker.prices
        assert tracker.prices['claude-sonnet-4']['input'] == 3.0

    def test_load_prices_from_file(self, temp_dir, monkeypatch):
        """Test loading prices from config file"""
        # Create a fake "scripts/" + "config/" layout under temp_dir so that
        # Path(__file__).parent.parent inside _load_prices points at temp_dir.
        scripts_dir = temp_dir / "scripts"
        scripts_dir.mkdir()
        config_dir = temp_dir / "config"
        config_dir.mkdir()
        prices_file = config_dir / "prices.json"

        custom_prices = {
            "claude-sonnet-4": {"input": 5.0, "output": 20.0}
        }
        with open(prices_file, 'w', encoding='utf-8') as f:
            json.dump(custom_prices, f)

        fake_module_path = str(scripts_dir / "cost_tracker.py")
        monkeypatch.setattr('scripts.cost_tracker.__file__', fake_module_path)

        db_path = temp_dir / "test.db"
        tracker = CostTracker(db_path)
        # Should use custom prices loaded from the temp config file
        assert tracker.prices['claude-sonnet-4']['input'] == 5.0


class TestTrackOperation:
    """Test operation tracking"""

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory"""
        temp_dir = Path(tempfile.mkdtemp())
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)

    @pytest.fixture
    def tracker(self, temp_dir):
        """Create tracker with temp database"""
        db_path = temp_dir / "test.db"
        return CostTracker(db_path)

    def test_track_operation_basic(self, tracker):
        """Test basic operation tracking"""
        result = tracker.track_operation(
            operation_type="test_op",
            input_tokens=1000,
            output_tokens=500
        )

        assert result['operation_type'] == "test_op"
        assert result['input_tokens'] == 1000
        assert result['output_tokens'] == 500
        assert result['total_cost'] > 0
        assert 'id' in result
        assert 'timestamp' in result

    def test_track_operation_cost_calculation(self, tracker):
        """Test cost calculation"""
        result = tracker.track_operation(
            operation_type="test",
            input_tokens=1_000_000,  # 1M tokens
            output_tokens=1_000_000,
            model='claude-sonnet-4'
        )

        # claude-sonnet-4: input=$3/M, output=$15/M
        expected_cost = 3.0 + 15.0
        assert abs(result['total_cost'] - expected_cost) < 0.01

    def test_track_operation_different_models(self, tracker):
        """Test tracking with different models"""
        opus_result = tracker.track_operation(
            operation_type="test",
            input_tokens=1_000_000,
            model='claude-opus-4'
        )

        haiku_result = tracker.track_operation(
            operation_type="test",
            input_tokens=1_000_000,
            model='claude-haiku-4'
        )

        # Opus should be more expensive than Haiku
        assert opus_result['total_cost'] > haiku_result['total_cost']

    def test_track_operation_with_metadata(self, tracker):
        """Test tracking with metadata"""
        result = tracker.track_operation(
            operation_type="test",
            input_tokens=100,
            metadata='{"user": "test"}'
        )

        assert result['id'] is not None


class TestGetStats:
    """Test statistics"""

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory"""
        temp_dir = Path(tempfile.mkdtemp())
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)

    @pytest.fixture
    def tracker(self, temp_dir):
        """Create tracker with temp database"""
        db_path = temp_dir / "test.db"
        return CostTracker(db_path)

    def test_get_stats_empty(self, tracker):
        """Test stats with no operations"""
        stats = tracker.get_stats(days=7)

        assert stats['total_operations'] == 0
        assert stats['total_input_tokens'] == 0
        assert stats['total_output_tokens'] == 0
        assert stats['total_cost'] == 0.0
        assert stats['operations_by_type'] == {}

    def test_get_stats_with_operations(self, tracker):
        """Test stats with operations"""
        # Track some operations
        tracker.track_operation("op1", input_tokens=1000, output_tokens=500)
        tracker.track_operation("op2", input_tokens=2000, output_tokens=1000)
        tracker.track_operation("op1", input_tokens=500, output_tokens=250)

        stats = tracker.get_stats(days=7)

        assert stats['total_operations'] == 3
        assert stats['total_input_tokens'] == 3500
        assert stats['total_output_tokens'] == 1750
        assert stats['total_cost'] > 0
        assert 'op1' in stats['operations_by_type']
        assert 'op2' in stats['operations_by_type']
        assert stats['operations_by_type']['op1']['count'] == 2
        assert stats['operations_by_type']['op2']['count'] == 1

    def test_get_stats_period(self, tracker):
        """Test stats for different periods"""
        tracker.track_operation("test", input_tokens=1000)

        stats_7d = tracker.get_stats(days=7)
        stats_30d = tracker.get_stats(days=30)

        assert stats_7d['period_days'] == 7
        assert stats_30d['period_days'] == 30
        # Both should include the operation
        assert stats_7d['total_operations'] == 1
        assert stats_30d['total_operations'] == 1

    def test_get_stats_includes_recent_operation_regardless_of_tz(self, tracker):
        """Recent operations must show up in get_stats() regardless of host UTC offset.

        Regression guard for the previous bug where stored timestamps were in
        local time but the WHERE cutoff used SQLite's UTC ``datetime('now', ...)``.
        On hosts with a non-UTC offset, operations from the last few hours could
        silently fall outside the window. The fix adds the ``'localtime'``
        modifier so both sides of the comparison are in the same zone.
        """
        tracker.track_operation("zone_check", input_tokens=10, output_tokens=5)

        # An operation just written must appear in the 1-day window on every
        # host, including UTC+12 / UTC-12 boxes. The assertion would fail under
        # the pre-fix code on a sufficiently-offset CI runner.
        stats = tracker.get_stats(days=1)
        assert stats['total_operations'] == 1
        assert stats['operations_by_type'].get('zone_check', {}).get('count') == 1


class TestPrintStats:
    """Test stats printing"""

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory"""
        temp_dir = Path(tempfile.mkdtemp())
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)

    @pytest.fixture
    def tracker(self, temp_dir):
        """Create tracker with temp database"""
        db_path = temp_dir / "test.db"
        return CostTracker(db_path)

    def test_print_stats_basic(self, tracker, capsys):
        """Test basic stats printing"""
        tracker.track_operation("test", input_tokens=1000, output_tokens=500)
        tracker.print_stats(days=7)

        captured = capsys.readouterr()
        assert "[COST STATISTICS]" in captured.out
        assert "Total operations: 1" in captured.out
        assert "test" in captured.out

    def test_print_stats_verbose(self, tracker, capsys):
        """Test verbose stats printing"""
        tracker.track_operation("test", input_tokens=1000)
        tracker.print_stats(days=7, verbose=True)

        captured = capsys.readouterr()
        assert "[VERBOSE]" in captured.out
        assert "Price configuration" in captured.out
        assert "claude-sonnet-4" in captured.out


class TestEdgeCases:
    """Test edge cases"""

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory"""
        temp_dir = Path(tempfile.mkdtemp())
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)

    @pytest.fixture
    def tracker(self, temp_dir):
        """Create tracker with temp database"""
        db_path = temp_dir / "test.db"
        return CostTracker(db_path)

    def test_track_zero_tokens(self, tracker):
        """Test tracking with zero tokens"""
        result = tracker.track_operation(
            operation_type="test",
            input_tokens=0,
            output_tokens=0
        )

        assert result['total_cost'] == 0.0

    def test_track_unknown_model(self, tracker):
        """Test tracking with unknown model"""
        result = tracker.track_operation(
            operation_type="test",
            input_tokens=1000,
            model='unknown-model'
        )

        # Should fallback to claude-sonnet-4 prices
        assert result['total_cost'] > 0

    def test_unicode_in_operation_type(self, tracker):
        """Test Unicode in operation type"""
        result = tracker.track_operation(
            operation_type="тест операция",
            input_tokens=100
        )

        assert result['operation_type'] == "тест операция"

    def test_large_token_counts(self, tracker):
        """Test with very large token counts"""
        result = tracker.track_operation(
            operation_type="large",
            input_tokens=100_000_000,  # 100M tokens
            output_tokens=50_000_000
        )

        assert result['total_cost'] > 0
        assert result['input_tokens'] == 100_000_000


class TestDatabaseIntegrity:
    """Test database integrity"""

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory"""
        temp_dir = Path(tempfile.mkdtemp())
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_database_created(self, temp_dir):
        """Test that database is created"""
        db_path = temp_dir / "test.db"
        CostTracker(db_path)

        assert db_path.exists()

    def test_database_schema(self, temp_dir):
        """Test database schema"""
        db_path = temp_dir / "test.db"
        tracker = CostTracker(db_path)

        # Track an operation to ensure schema is correct
        result = tracker.track_operation("test", input_tokens=100)
        assert result['id'] is not None

    def test_concurrent_access(self, temp_dir):
        """Test concurrent database access"""
        db_path = temp_dir / "test.db"
        tracker1 = CostTracker(db_path)
        tracker2 = CostTracker(db_path)

        tracker1.track_operation("op1", input_tokens=100)
        tracker2.track_operation("op2", input_tokens=200)

        stats = tracker1.get_stats()
        assert stats['total_operations'] == 2


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
