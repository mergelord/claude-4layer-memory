#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for semantic_search.py fallback paths."""

import subprocess
import sys
import os
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
import semantic_search


class TestExecuteSemanticSearch:
    @patch('semantic_search.subprocess.run')
    @patch('semantic_search.safe_path')
    @patch('semantic_search.logging')
    def test_timeout(self, mock_logging, mock_safe_path, mock_run):
        mock_safe_path.return_value = MagicMock(exists=lambda: True, is_file=lambda: True)
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="dummy", timeout=30)
        semantic_search.execute_semantic_search("test query", "как мы")
        mock_logging.error.assert_called_once_with("Semantic search timed out")

    @patch('semantic_search.subprocess.run')
    @patch('semantic_search.safe_path')
    @patch('semantic_search.logging')
    def test_file_not_found(self, mock_logging, mock_safe_path, mock_run):
        mock_safe_path.return_value = MagicMock(exists=lambda: False)
        semantic_search.execute_semantic_search("test query", "как мы")
        mock_logging.error.assert_called_once()
        assert "not found" in mock_logging.error.call_args[0][0].lower()

    @patch('semantic_search.subprocess.run')
    @patch('semantic_search.safe_path')
    @patch('semantic_search.logging')
    def test_subprocess_error(self, mock_logging, mock_safe_path, mock_run):
        mock_safe_path.return_value = MagicMock(exists=lambda: True, is_file=lambda: True)
        mock_run.side_effect = subprocess.CalledProcessError(1, "dummy", b"", b"error output")
        semantic_search.execute_semantic_search("test query", "как мы")
        mock_logging.error.assert_called_once()
        assert "Semantic search failed" in mock_logging.error.call_args[0][0]

    @patch('semantic_search.subprocess.run')
    @patch('semantic_search.safe_path')
    @patch('semantic_search.logging')
    def test_os_error(self, mock_logging, mock_safe_path, mock_run):
        mock_safe_path.return_value = MagicMock(exists=lambda: True, is_file=lambda: True)
        mock_run.side_effect = OSError("Some OS error")
        semantic_search.execute_semantic_search("test query", "как мы")
        mock_logging.error.assert_called_once()
        assert "Semantic search failed" in mock_logging.error.call_args[0][0]

    @patch('semantic_search.subprocess.run')
    @patch('semantic_search.safe_path')
    @patch('semantic_search.logging')
    def test_unsafe_path(self, mock_logging, mock_safe_path, mock_run):
        mock_safe_path.side_effect = ValueError("Path /etc/passwd is outside home directory")
        semantic_search.execute_semantic_search("test query", "как мы")
        mock_logging.error.assert_called_once()
        assert "Failed to find L4 script" in mock_logging.error.call_args[0][0]


class TestSafeExecuteSubprocess:
    def test_script_not_found(self, tmp_path):
        fake_script = tmp_path / "nonexistent.py"
        with pytest.raises(FileNotFoundError):
            semantic_search.safe_execute_subprocess(fake_script, "query")

    def test_script_no_read_access(self, tmp_path):
        fake_script = tmp_path / "unreadable.py"
        fake_script.touch(mode=0o200)
        with pytest.raises(PermissionError):
            semantic_search.safe_execute_subprocess(fake_script, "query")

    def test_successful_call(self, tmp_path):
        fake_script = tmp_path / "success.py"
        fake_script.write_text("print('hello')")
        with patch('semantic_search.subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="[SEARCH ALL] result", stderr="")
            result = semantic_search.safe_execute_subprocess(fake_script, "query")
        assert result.returncode == 0
        assert mock_run.called
        call_args = mock_run.call_args[0][0]
        assert "search-all" in call_args
        assert "query" in call_args
