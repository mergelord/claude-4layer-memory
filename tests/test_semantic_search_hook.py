#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for semantic_search.py hook contract."""

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
import semantic_search


@pytest.fixture
def dummy_script(tmp_path):
    script = tmp_path / "dummy.py"
    script.write_text("# dummy script")
    return script


def _make_run_result(stdout: str, returncode: int = 0, stderr: str = "") -> MagicMock:
    m = MagicMock()
    m.stdout = stdout
    m.returncode = returncode
    m.stderr = stderr
    return m


class TestShouldSearch:
    def test_russian_triggers(self):
        assert semantic_search.should_search("как мы это сделали?")[0] is True
        assert semantic_search.should_search("помнишь наше решение?")[0] is True
        assert semantic_search.should_search("что мы решили по этому вопросу")[0] is True
        assert semantic_search.should_search("ты рекомендовал использовать Redis")[0] is True

    def test_english_triggers(self):
        assert semantic_search.should_search("remember what we decided?")[0] is True
        assert semantic_search.should_search("previously we used a different approach")[0] is True
        assert semantic_search.should_search("what did we decide about caching?")[0] is True

    def test_no_trigger(self):
        found, _ = semantic_search.should_search("please fix the typo in README")
        assert found is False

    def test_returns_trigger_phrase(self):
        found, trigger = semantic_search.should_search("remember the login bug?")
        assert found is True
        assert trigger != ""


class TestExecuteSemanticSearch:
    def test_successful_json_with_results(self, capsys, dummy_script):
        payload = json.dumps({
            "results": [
                {
                    "key": "global/notes.md",
                    "source": "global",
                    "text": "We decided to use ChromaDB for semantic search.",
                    "distance": 0.12,
                    "metadata": {"file": "notes.md"},
                }
            ]
        })
        with patch("semantic_search.safe_path", return_value=dummy_script):
            with patch("semantic_search.subprocess.run", return_value=_make_run_result(payload)):
                semantic_search.execute_semantic_search("how did we store memory?", "how did we")

        out = capsys.readouterr().out
        assert "how did we store memory?" in out
        assert "<semantic_context>" in out
        assert "</semantic_context>" in out
        assert "notes.md" in out

    def test_empty_json_results_no_context_block(self, capsys, dummy_script):
        payload = json.dumps({"results": []})
        with patch("semantic_search.safe_path", return_value=dummy_script):
            with patch("semantic_search.subprocess.run", return_value=_make_run_result(payload)):
                semantic_search.execute_semantic_search("how did we store memory?", "how did we")

        out = capsys.readouterr().out
        assert "how did we store memory?" in out
        assert "<semantic_context>" not in out

    def test_invalid_json_falls_back_to_prompt(self, capsys, dummy_script):
        with patch("semantic_search.safe_path", return_value=dummy_script):
            with patch("semantic_search.subprocess.run",
                       return_value=_make_run_result("not valid json")):
                with patch("semantic_search.logging"):
                    semantic_search.execute_semantic_search("my query", "my")

        out = capsys.readouterr().out
        assert "my query" in out
        assert "<semantic_context>" not in out

    def test_nonzero_returncode_falls_back(self, capsys, dummy_script):
        with patch("semantic_search.safe_path", return_value=dummy_script):
            with patch("semantic_search.subprocess.run",
                       return_value=_make_run_result("", returncode=1, stderr="some error")):
                with patch("semantic_search.logging"):
                    semantic_search.execute_semantic_search("my query", "my")

        out = capsys.readouterr().out
        assert "my query" in out
        assert "<semantic_context>" not in out

    def test_subprocess_args_include_json_flag(self, dummy_script):
        payload = json.dumps({"results": []})
        with patch("semantic_search.safe_path", return_value=dummy_script):
            with patch("semantic_search.subprocess.run",
                       return_value=_make_run_result(payload)) as mock_run:
                semantic_search.execute_semantic_search("test prompt", "test")

        args = mock_run.call_args[0][0]
        assert args[0] == sys.executable
        assert args[2] == "search-all"
        assert args[3] == "test prompt"
        assert "--json" in args

    @patch("semantic_search.logging")
    def test_timeout_falls_back(self, mock_logging, dummy_script):
        with patch("semantic_search.safe_path", return_value=dummy_script):
            with patch("semantic_search.subprocess.run",
                       side_effect=subprocess.TimeoutExpired(cmd="dummy", timeout=30)):
                semantic_search.execute_semantic_search("test query", "как мы")
        mock_logging.warning.assert_called_once_with(
            "Semantic search fallback (%s): %s",
            "timeout",
            "L4 search exceeded 30s budget for trigger 'как мы'",
        )

    @patch("semantic_search.logging")
    def test_file_not_found(self, mock_logging, dummy_script):
        not_found = dummy_script.with_name("nonexistent.py")
        with patch("semantic_search.safe_path", return_value=not_found):
            semantic_search.execute_semantic_search("test query", "как мы")
        mock_logging.warning.assert_called_once()
        assert "not found" in str(mock_logging.warning.call_args)

    @patch("semantic_search.logging")
    def test_subprocess_error_falls_back(self, mock_logging, dummy_script):
        with patch("semantic_search.safe_path", return_value=dummy_script):
            with patch("semantic_search.subprocess.run",
                       side_effect=subprocess.SubprocessError("subprocess failed")):
                semantic_search.execute_semantic_search("test query", "как мы")
        mock_logging.warning.assert_called_once()
        assert "subprocess_error" in str(mock_logging.warning.call_args)

    @patch("semantic_search.logging")
    def test_os_error_falls_back(self, mock_logging, dummy_script):
        with patch("semantic_search.safe_path", return_value=dummy_script):
            with patch("semantic_search.subprocess.run",
                       side_effect=OSError("OS error")):
                semantic_search.execute_semantic_search("test query", "как мы")
        mock_logging.warning.assert_called_once()
        assert "OS error" in str(mock_logging.warning.call_args)

    @patch("semantic_search.logging")
    def test_unsafe_path_falls_back(self, mock_logging):
        with patch("semantic_search.safe_path",
                   side_effect=ValueError("Path /etc/passwd is outside home directory")):
            semantic_search.execute_semantic_search("test query", "как мы")
        mock_logging.warning.assert_called_once()
        assert "unsafe_path" in str(mock_logging.warning.call_args)

    @patch("semantic_search.logging")
    def test_permission_error_falls_back(self, mock_logging, dummy_script):
        with patch("semantic_search.safe_path", return_value=dummy_script):
            with patch("semantic_search.subprocess.run",
                       side_effect=PermissionError("permission denied")):
                semantic_search.execute_semantic_search("test query", "как мы")
        mock_logging.warning.assert_called_once()
        assert "no_access" in str(mock_logging.warning.call_args)
