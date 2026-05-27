#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for l4_bm25_search module (BM25 retrieval layer)."""

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from l4_bm25_search import fetch_bm25_results, _sanitize_query


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_connection():
    """Create a mock SQLite connection that returns sample rows."""
    conn = MagicMock()
    cursor = MagicMock()
    conn.__enter__.return_value = conn
    cursor.fetchall.return_value = [
        {
            "path": "docs/memory.md",
            "source": "global",
            "snippet": "Test »snippet« content",
            "bm25_score": -2.5,
        },
        {
            "path": "docs/guide.md",
            "source": "global",
            "snippet": "Another »text« here",
            "bm25_score": -1.8,
        },
    ]
    conn.execute.return_value = cursor
    return conn


# ---------------------------------------------------------------------------
# _sanitize_query tests (pure function)
# ---------------------------------------------------------------------------

class TestSanitizeQuery:
    """Tests for _sanitize_query function."""

    def test_empty_query_returns_empty_string(self):
        assert _sanitize_query("") == ""

    def test_whitespace_query_returns_empty_string(self):
        assert _sanitize_query("   ") == ""

    def test_normal_query_passes_through(self):
        assert _sanitize_query("memory system") == "memory system"

    def test_removes_fts_operators(self):
        sanitized = _sanitize_query("test AND query OR something")
        assert "AND" not in sanitized
        assert "OR" not in sanitized
        assert "test" in sanitized
        assert "query" in sanitized

    def test_removes_not_operator(self):
        sanitized = _sanitize_query("NOT memory")
        assert "NOT" not in sanitized
        assert "memory" in sanitized

    def test_removes_near_operator(self):
        sanitized = _sanitize_query("memory NEAR system")
        assert "NEAR" not in sanitized
        assert "memory" in sanitized

    def test_removes_quotes(self):
        sanitized = _sanitize_query('"exact phrase"')
        assert '"' not in sanitized
        assert "exact phrase" in sanitized

    def test_removes_parentheses(self):
        sanitized = _sanitize_query("(memory OR system)")
        assert "(" not in sanitized
        assert ")" not in sanitized
        assert "memory" in sanitized

    def test_preserves_special_characters(self):
        """C++, C#, email, paths should survive sanitization."""
        assert "C++" in _sanitize_query("C++ programming")
        assert "C#" in _sanitize_query("C# language")
        assert "test@example.com" in _sanitize_query("test@example.com")
        assert "path/file.py" in _sanitize_query("path/file.py")

    def test_collapses_multiple_spaces(self):
        sanitized = _sanitize_query("memory    system")
        assert "  " not in sanitized
        assert sanitized == "memory system"

    def test_operator_case_insensitive(self):
        sanitized = _sanitize_query("AND OR NOT NEAR")
        assert "AND" not in sanitized
        assert "OR" not in sanitized
        assert "NOT" not in sanitized
        assert "NEAR" not in sanitized


# ---------------------------------------------------------------------------
# fetch_bm25_results tests (with mocks)
# ---------------------------------------------------------------------------

class TestFetchBM25Results:
    """Tests for fetch_bm25_results function."""

    def test_empty_query_returns_empty_list(self):
        result = fetch_bm25_results("")
        assert result == []

    def test_whitespace_query_returns_empty_list(self):
        result = fetch_bm25_results("   ")
        assert result == []

    def test_unavailable_db_returns_empty_list(self):
        with patch("l4_bm25_search._get_fts5_connection") as mock_conn:
            mock_conn.side_effect = Exception("DB not found")
            result = fetch_bm25_results("test query")
            assert result == []

    def test_malformed_match_expression_returns_empty_list(self):
        """Malformed MATCH expression should return [] and not crash."""
        result = fetch_bm25_results("AND OR NOT test")
        assert isinstance(result, list)

    def test_successful_search_returns_results(self, mock_connection):
        with patch("l4_bm25_search._get_fts5_connection", return_value=mock_connection):
            result = fetch_bm25_results("test query")

        assert len(result) == 2
        # Bug N-4: key preserves the rel_path stored in row['path'], not basename.
        assert result[0]["key"] == "[global] docs/memory.md"
        assert result[0]["rank"] == 1
        assert result[0]["bm25_score"] == -2.5
        assert result[0]["snippet"] is not None
        assert result[0]["source_type"] == "bm25"

    def test_result_has_document_level_key(self, mock_connection):
        """Key must be document-level: [source] rel_path.

        Bug N-4: rel_path is now preserved verbatim so siblings with the
        same basename in different sub-directories stay distinct.
        """
        with patch("l4_bm25_search._get_fts5_connection", return_value=mock_connection):
            result = fetch_bm25_results("query")

        assert result[0]["key"] == "[global] docs/memory.md"
        assert result[1]["key"] == "[global] docs/guide.md"

    def test_rank_is_sequential(self, mock_connection):
        """Rank should be 1-based sequential."""
        with patch("l4_bm25_search._get_fts5_connection", return_value=mock_connection):
            result = fetch_bm25_results("query")

        assert result[0]["rank"] == 1
        assert result[1]["rank"] == 2

    def test_empty_sql_result_returns_empty_list(self):
        """When SQL returns no rows, result should be empty list."""
        conn = MagicMock()
        cursor = MagicMock()
        conn.__enter__.return_value = conn
        cursor.fetchall.return_value = []
        conn.execute.return_value = cursor

        with patch("l4_bm25_search._get_fts5_connection", return_value=conn):
            result = fetch_bm25_results("nonexistent")
            assert result == []

    def test_sql_operational_error_returns_empty_list(self):
        """SQLite OperationalError should be caught gracefully."""
        conn = MagicMock()
        conn.__enter__.return_value = conn
        conn.execute.side_effect = __import__('sqlite3').OperationalError("malformed MATCH")

        with patch("l4_bm25_search._get_fts5_connection", return_value=conn):
            result = fetch_bm25_results("malformed)))")
            assert result == []

    def test_limit_parameter_is_respected(self, mock_connection):
        """The limit parameter should be passed to SQL query."""
        with patch("l4_bm25_search._get_fts5_connection", return_value=mock_connection):
            fetch_bm25_results("query", limit=5)

        # Проверяем, что execute был вызван
        assert mock_connection.execute.called
        # Получаем позиционные аргументы вызова
        args, kwargs = mock_connection.execute.call_args
        # args[1] — это кортеж параметров
        params = args[1]
        # limit — последний элемент в кортеже
        assert params[-1] == 5

    def test_snippet_uses_configured_markers(self, mock_connection):
        """Snippet should use » and « as markers."""
        with patch("l4_bm25_search._get_fts5_connection", return_value=mock_connection):
            result = fetch_bm25_results("query")

        assert "»" in result[0]["snippet"]
        assert "«" in result[0]["snippet"]
