"""
Basic smoke tests for scripts
"""
import subprocess
import sys
from pathlib import Path


def test_memory_lint_help():
    """Test memory_lint.py --help"""
    result = subprocess.run(
        [sys.executable, 'scripts/memory_lint.py', '--help'],
        capture_output=True,
        text=True
    )
    assert result.returncode == 0
    assert 'Memory Lint' in result.stdout or 'usage' in result.stdout


def test_audit_help():
    """Test audit.py --help"""
    result = subprocess.run(
        [sys.executable, 'audit.py', '--help'],
        capture_output=True,
        text=True
    )
    assert result.returncode == 0
    assert 'usage' in result.stdout or 'audit' in result.stdout.lower()


def test_scripts_exist():
    """Test that all main scripts exist"""
    scripts = [
        'scripts/memory_lint.py',
        'audit.py',
        'scripts/l4_semantic_global.py'
    ]

    for script in scripts:
        assert Path(script).exists(), f"Script {script} not found"
