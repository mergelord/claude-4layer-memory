#!/usr/bin/env python3
"""
Tests for health_memory_size.py

Validates that memory system stays within healthy thresholds.
"""

import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent
HEALTH_SCRIPT = PROJECT_ROOT / "scripts" / "health_memory_size.py"


def test_health_script_exists():
    """Health check script must exist."""
    assert HEALTH_SCRIPT.exists(), f"Health script not found: {HEALTH_SCRIPT}"


def test_health_script_executable():
    """Health check script must be executable."""
    result = subprocess.run(
        [sys.executable, str(HEALTH_SCRIPT)],
        capture_output=True, text=True, timeout=30,
    )
    # Должен быть какой-то вывод (или stderr если упал)
    assert result.stdout or result.stderr, "No output from health check script"
    assert len(result.stdout or result.stderr) > 0


def test_health_check_passes():
    """Health check should pass (exit code 0) in CI environment.

    This test will fail if:
    - HOT layer has > 20 entries
    - MEMORY.md has > 200 lines
    - ChromaDB has > 10,000 documents
    """
    result = subprocess.run(
        [sys.executable, str(HEALTH_SCRIPT)],
        capture_output=True, text=True, timeout=30,
    )

    # Exit code 0 = все проверки прошли
    # Exit code 1 = есть алерты
    if result.returncode != 0:
        pytest.fail(
            f"Health check failed with alerts:\n{result.stdout}\n{result.stderr}"
        )


def test_health_check_output_format():
    """Health check output should contain expected sections."""
    result = subprocess.run(
        [sys.executable, str(HEALTH_SCRIPT)],
        capture_output=True, text=True, timeout=30,
    )

    output = result.stdout or result.stderr or ""

    # Должен быть заголовок
    assert "Memory Health Check" in output, f"Missing header. Output: {output[:200]}"

    # Должны быть проверки (ищем текстовые маркеры вместо emoji)
    assert any(marker in output for marker in ["HOT", "MEMORY.md", "ChromaDB", "All health checks passed"]), \
        f"Missing expected markers. Output: {output[:200]}"


def test_health_check_timeout():
    """Health check should complete within reasonable time."""
    import time
    start = time.time()

    result = subprocess.run(
        [sys.executable, str(HEALTH_SCRIPT)],
        capture_output=True, text=True, timeout=30,
    )

    elapsed = time.time() - start

    # Не должен занимать больше 10 секунд
    assert elapsed < 10, f"Health check took too long: {elapsed:.2f}s"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
