"""Contract tests for ``scripts/validate_rrf.py``'s testable ``main``.

These do not check the human-readable output verbatim - they pin the
*return-code contract* of :func:`scripts.validate_rrf.main` so the CLI
remains programmatically callable (no uncaught :class:`SystemExit`
escapes from input-validation paths).
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

import pytest

# Make scripts/ importable.
_SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

# pylint: disable=wrong-import-position
import validate_rrf  # noqa: E402


def test_main_returns_zero_on_default_invocation(capsys):
    """``main([])`` runs all canonical scenarios and returns 0."""
    rc = validate_rrf.main([])
    captured = capsys.readouterr()
    assert rc == 0
    assert "Case 1" in captured.out
    assert "Case 2" in captured.out
    assert "Case 3" in captured.out


def test_main_returns_zero_for_single_scenario(capsys):
    rc = validate_rrf.main(["--scenario", "many_weak_vs_one_strong"])
    captured = capsys.readouterr()
    assert rc == 0
    assert "Case 3" in captured.out
    assert "Case 1" not in captured.out


def test_main_rejects_negative_k_with_return_code_two(capsys):
    rc = validate_rrf.main(["--k", "-1"])
    captured = capsys.readouterr()
    assert rc == 2
    assert "must be non-negative" in captured.err


def test_main_stdin_rejects_empty_payload_with_return_code_two(monkeypatch, capsys):
    """Empty stdin must NOT raise SystemExit - it must return 2."""
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    rc = validate_rrf.main(["--stdin"])
    captured = capsys.readouterr()
    assert rc == 2
    assert "requires a JSON payload" in captured.err


def test_main_stdin_rejects_invalid_json_with_return_code_two(monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO("{not valid json"))
    rc = validate_rrf.main(["--stdin"])
    captured = capsys.readouterr()
    assert rc == 2
    assert "invalid JSON" in captured.err


def test_main_stdin_rejects_wrong_field_types_with_return_code_two(monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO('{"fts": "oops", "semantic": []}'))
    rc = validate_rrf.main(["--stdin"])
    captured = capsys.readouterr()
    assert rc == 2
    assert "list-typed" in captured.err


def test_main_stdin_accepts_valid_payload_and_returns_zero(monkeypatch, capsys):
    payload = '{"fts": [{"key": "a.md"}, {"key": "b.md"}], "semantic": [{"key": "b.md"}]}'
    monkeypatch.setattr("sys.stdin", io.StringIO(payload))
    rc = validate_rrf.main(["--stdin"])
    captured = capsys.readouterr()
    assert rc == 0
    assert "Custom payload from stdin" in captured.out
    assert "a.md" in captured.out
    assert "b.md" in captured.out


def test_main_no_uncaught_systemexit_on_any_error_path(monkeypatch):
    """Exhaustive contract check: error paths must not raise SystemExit.

    A programmatic caller (test harness, MCP wrapper, etc.) should
    receive an int return code instead of having to wrap calls in
    ``try/except SystemExit``.
    """
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    try:
        rc = validate_rrf.main(["--stdin"])
    except SystemExit as exc:  # pragma: no cover - if this fires the test fails
        pytest.fail(f"main() leaked SystemExit({exc.code}) instead of returning")
    assert rc == 2
