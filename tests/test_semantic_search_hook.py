"""Robustness tests for ``scripts/semantic_search.py``.

These pin the contract that the SessionStart hook NEVER raises and
ALWAYS prints the original user prompt to stdout, regardless of how
the underlying L4 subprocess fails. Each fallback path also emits a
distinct ``reason`` tag to stderr so log triage can tell apart:

* ``timeout``           - L4 took longer than the budget
* ``not_found``         - L4 script (or interpreter) is missing
* ``no_access``         - L4 script exists but is unreadable
* ``unsafe_path``       - configured L4 path escapes ``$HOME``
* ``subprocess_error``  - generic ``SubprocessError`` from ``run``
* ``os_error``          - low-level OS error around process launch

These tags double as regression guards: a future refactor that rewires
the catch order or collapses paths back into a generic ``Exception``
handler will fail one of these tests.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Make scripts/ importable.
_SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

# pylint: disable=wrong-import-position
import semantic_search  # noqa: E402


@pytest.fixture
def fake_l4_script(tmp_path: Path, monkeypatch):
    """Place a readable dummy L4 script inside $HOME so safe_path passes."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))

    script = home / "l4.py"
    script.write_text("# placeholder", encoding="utf-8")

    monkeypatch.setitem(semantic_search.CONFIG, "l4_script", str(script))
    return script


# ---------------------------------------------------------------------------
# Happy path - sanity check
# ---------------------------------------------------------------------------


def test_execute_search_emits_context_when_l4_returns_results(
    fake_l4_script, capsys, monkeypatch
):
    """When the L4 subprocess returns a ``[SEARCH ALL]`` block the hook
    wraps it in ``<semantic_context>`` and emits both the prompt and the
    context to stdout."""
    completed = subprocess.CompletedProcess(
        args=[], returncode=0, stdout="[SEARCH ALL]\nfound something\n", stderr=""
    )
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: completed)

    semantic_search.execute_semantic_search("how did we", "how did we")
    out = capsys.readouterr().out
    assert "<semantic_context>" in out
    assert "[SEARCH ALL]" in out
    assert "found something" in out


def test_execute_search_emits_only_prompt_when_l4_returns_no_results(
    fake_l4_script, capsys, monkeypatch
):
    completed = subprocess.CompletedProcess(
        args=[], returncode=0, stdout="(no matches)", stderr=""
    )
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: completed)

    semantic_search.execute_semantic_search("how did we", "how did we")
    out = capsys.readouterr().out
    assert "<semantic_context>" not in out
    assert "how did we" in out


# ---------------------------------------------------------------------------
# Fallback contract - each failure mode must produce a distinct reason tag
# AND must not raise out of the hook.
# ---------------------------------------------------------------------------


def _raise(exc):
    """Return a callable that raises ``exc`` regardless of arguments."""
    def _inner(*_args, **_kwargs):
        raise exc
    return _inner


def test_timeout_falls_back_with_timeout_reason(
    fake_l4_script, capsys, monkeypatch
):
    """A real ``subprocess.TimeoutExpired`` from ``run`` must be caught
    explicitly (not via generic ``Exception``) and produce reason=timeout."""
    monkeypatch.setattr(
        subprocess,
        "run",
        _raise(subprocess.TimeoutExpired(cmd="l4", timeout=30.0)),
    )

    semantic_search.execute_semantic_search("how did we", "how did we")
    captured = capsys.readouterr()
    assert "how did we" in captured.out
    assert "timeout" in captured.err
    assert "30s" in captured.err


def test_timeout_does_not_raise_into_caller(fake_l4_script, monkeypatch):
    monkeypatch.setattr(
        subprocess,
        "run",
        _raise(subprocess.TimeoutExpired(cmd="l4", timeout=30.0)),
    )
    # Hook must absorb the exception entirely.
    semantic_search.execute_semantic_search("how did we", "how did we")


def test_missing_l4_script_falls_back_with_not_found_reason(
    tmp_path, capsys, monkeypatch
):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    # Point at a path inside $HOME that does not exist.
    monkeypatch.setitem(
        semantic_search.CONFIG, "l4_script", str(home / "missing.py")
    )

    semantic_search.execute_semantic_search("how did we", "how did we")
    captured = capsys.readouterr()
    assert "how did we" in captured.out
    assert "not_found" in captured.err


def test_unreadable_l4_script_falls_back_with_no_access_reason(
    fake_l4_script, capsys, monkeypatch
):
    monkeypatch.setattr(os, "access", lambda path, mode: False)

    semantic_search.execute_semantic_search("how did we", "how did we")
    captured = capsys.readouterr()
    assert "how did we" in captured.out
    assert "no_access" in captured.err


def test_subprocess_error_falls_back_with_subprocess_error_reason(
    fake_l4_script, capsys, monkeypatch
):
    monkeypatch.setattr(
        subprocess, "run", _raise(subprocess.SubprocessError("boom"))
    )

    semantic_search.execute_semantic_search("how did we", "how did we")
    captured = capsys.readouterr()
    assert "how did we" in captured.out
    assert "subprocess_error" in captured.err


def test_oserror_at_launch_falls_back_with_os_error_reason(
    fake_l4_script, capsys, monkeypatch
):
    monkeypatch.setattr(subprocess, "run", _raise(OSError("ENOENT")))

    semantic_search.execute_semantic_search("how did we", "how did we")
    captured = capsys.readouterr()
    assert "how did we" in captured.out
    assert "os_error" in captured.err


def test_unsafe_path_falls_back_with_unsafe_path_reason(
    tmp_path, capsys, monkeypatch
):
    """Configured L4 script outside $HOME triggers ValueError from
    safe_path; the hook must convert that to reason=unsafe_path."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))

    # Path resolves outside $HOME.
    outside = tmp_path / "outside" / "l4.py"
    outside.parent.mkdir()
    outside.write_text("", encoding="utf-8")
    monkeypatch.setitem(semantic_search.CONFIG, "l4_script", str(outside))

    semantic_search.execute_semantic_search("how did we", "how did we")
    captured = capsys.readouterr()
    assert "how did we" in captured.out
    assert "unsafe_path" in captured.err


# ---------------------------------------------------------------------------
# Logging contract - every fallback should emit a structured warning so
# operators can grep ``hooks/semantic_search.log`` for failure modes.
# ---------------------------------------------------------------------------


def test_timeout_emits_structured_warning_log(fake_l4_script, monkeypatch):
    monkeypatch.setattr(
        subprocess,
        "run",
        _raise(subprocess.TimeoutExpired(cmd="l4", timeout=30.0)),
    )

    with patch("semantic_search.logging") as mock_logging:
        semantic_search.execute_semantic_search("how did we", "how did we")

    mock_logging.warning.assert_called_once()
    args, _ = mock_logging.warning.call_args
    fmt, reason, _detail = args
    assert "fallback" in fmt
    assert reason == "timeout"


# ---------------------------------------------------------------------------
# Full main() entrypoint contract - exit code stays 0, no stack trace
# escapes even when the hook is invoked end-to-end.
# ---------------------------------------------------------------------------


def test_main_returns_zero_when_no_trigger_present(monkeypatch, capsys):
    monkeypatch.setattr(semantic_search, "read_user_prompt", lambda: "hello")
    rc = semantic_search.main()
    assert rc == 0
    assert capsys.readouterr().out.strip() == "hello"


def test_main_returns_zero_when_subprocess_times_out(
    fake_l4_script, monkeypatch, capsys
):
    monkeypatch.setattr(
        semantic_search, "read_user_prompt", lambda: "remember when we"
    )
    monkeypatch.setattr(
        subprocess,
        "run",
        _raise(subprocess.TimeoutExpired(cmd="l4", timeout=30.0)),
    )

    rc = semantic_search.main()
    captured = capsys.readouterr()
    assert rc == 0
    assert "remember when we" in captured.out
    assert "timeout" in captured.err
