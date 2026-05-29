#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Regression tests for AUDIT #5 (semantic slice).

Verifies that the blanket ``except Exception`` blocks in
``l4_semantic_global`` were narrowed to recoverable Chroma lookup/query
errors so that:

- expected Chroma failures (missing collection / lookup error) degrade
  gracefully (return ``None`` / skip the collection, log), and
- unexpected errors (programming bugs) now propagate instead of being
  silently swallowed.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Mock heavy deps before importing the module under test.
sys.modules.setdefault("sentence_transformers", MagicMock())
sys.modules.setdefault("chromadb", MagicMock())
sys.modules.setdefault("chromadb.config", MagicMock())

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import l4_semantic_global  # noqa: E402
from l4_semantic_global import GlobalSemanticMemory  # noqa: E402


def _make_memory():
    """GlobalSemanticMemory with mocked model + Chroma client (no __init__)."""
    mem = GlobalSemanticMemory.__new__(GlobalSemanticMemory)
    mem.model = MagicMock()
    emb = MagicMock()
    emb.tolist.return_value = [0.1, 0.2]
    mem.model.encode.return_value = [emb]
    mem.client = MagicMock()
    mem.collection_prefix = "memory_"
    mem.global_collection = "memory_global"
    return mem


class TestChromaLookupErrorsConstant:
    """_CHROMA_LOOKUP_ERRORS must be a safe tuple of exception classes."""

    def test_includes_value_and_key_error(self):
        assert ValueError in l4_semantic_global._CHROMA_LOOKUP_ERRORS
        assert KeyError in l4_semantic_global._CHROMA_LOOKUP_ERRORS

    def test_only_contains_exception_classes(self):
        for exc in l4_semantic_global._CHROMA_LOOKUP_ERRORS:
            assert isinstance(exc, type)
            assert issubclass(exc, BaseException)


class TestGetCollection:
    """_get_collection narrows the swallowed error set."""

    def test_missing_collection_returns_none(self):
        mem = _make_memory()
        mem.client.get_collection.side_effect = ValueError("does not exist")
        assert mem._get_collection("memory_global") is None

    def test_unexpected_error_propagates(self):
        mem = _make_memory()
        mem.client.get_collection.side_effect = RuntimeError("boom")
        with pytest.raises(RuntimeError):
            mem._get_collection("memory_global")


class TestSearchAllGracefulDegradation:
    """search_all isolates per-collection Chroma failures but not real bugs."""

    def test_project_collection_failure_is_skipped(self):
        mem = _make_memory()

        good = MagicMock()
        good.query.return_value = {
            "ids": [["g1"]],
            "documents": [["global text"]],
            "metadatas": [[{"file": "g.md"}]],
            "distances": [[0.1]],
        }
        bad = MagicMock()
        bad.query.side_effect = ValueError("collection corrupt")

        def get_collection(name):
            return good if name == "memory_global" else bad

        mem.client.get_collection.side_effect = get_collection

        proj = MagicMock()
        proj.name = "memory_proj"
        mem.client.list_collections.return_value = [proj]

        results = mem.search_all("query", n_results=5)
        keys = [r["key"] for r in results]
        assert "[global] g.md" in keys
        assert all("proj" not in k for k in keys)

    def test_global_collection_failure_degrades(self):
        mem = _make_memory()
        bad = MagicMock()
        bad.query.side_effect = ValueError("global corrupt")
        mem.client.get_collection.side_effect = lambda name: bad
        mem.client.list_collections.return_value = []

        # Should not raise; degrades to an empty result set.
        assert mem.search_all("query") == []

    def test_unexpected_project_error_propagates(self):
        mem = _make_memory()
        good = MagicMock()
        good.query.return_value = {
            "ids": [[]],
            "documents": [[]],
            "metadatas": [[]],
            "distances": [[]],
        }
        bad = MagicMock()
        bad.query.side_effect = RuntimeError("boom")

        def get_collection(name):
            return good if name == "memory_global" else bad

        mem.client.get_collection.side_effect = get_collection
        proj = MagicMock()
        proj.name = "memory_proj"
        mem.client.list_collections.return_value = [proj]

        with pytest.raises(RuntimeError):
            mem.search_all("query")


class TestIndexDirectoryReadErrors:
    """index_directory only swallows read/decoding errors."""

    def test_unicode_decode_error_is_skipped(self, tmp_path, monkeypatch):
        mem = _make_memory()
        collection = MagicMock()
        mem.client.get_or_create_collection.return_value = collection

        (tmp_path / "bad.md").write_text("content", encoding="utf-8")

        def boom(*_args, **_kwargs):
            raise UnicodeDecodeError("utf-8", b"", 0, 1, "bad")

        monkeypatch.setattr(Path, "read_text", boom)

        mem.index_directory(tmp_path, "memory_test")
        collection.upsert.assert_not_called()

    def test_unexpected_read_error_propagates(self, tmp_path, monkeypatch):
        mem = _make_memory()
        collection = MagicMock()
        mem.client.get_or_create_collection.return_value = collection

        (tmp_path / "bad.md").write_text("content", encoding="utf-8")

        def boom(*_args, **_kwargs):
            raise RuntimeError("boom")

        monkeypatch.setattr(Path, "read_text", boom)

        with pytest.raises(RuntimeError):
            mem.index_directory(tmp_path, "memory_test")
