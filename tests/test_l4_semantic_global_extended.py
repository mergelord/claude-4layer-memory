#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Extended tests for L4 Semantic Global Memory.

Covers:
- _make_document_key (document‑level key formation)
- index_directory (chunking, metadata, edge cases)
- search_all aggregation (document‑level grouping)
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock
import pytest

# Мокаем sentence‑transformers и chromadb ДО импорта нашего модуля
sys.modules['sentence_transformers'] = MagicMock()
sys.modules['chromadb'] = MagicMock()
sys.modules['chromadb.config'] = MagicMock()

# Добавляем путь к scripts перед импортом
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from l4_semantic_global import GlobalSemanticMemory  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def memory():
    """Create a GlobalSemanticMemory instance with mocked dependencies."""
    mem = GlobalSemanticMemory.__new__(GlobalSemanticMemory)
    # Модель
    mem.model = MagicMock()
    emb_mock = MagicMock()
    emb_mock.tolist.return_value = [0.1, 0.2, 0.3]
    mem.model.encode.return_value = [emb_mock]
    # ChromaDB клиент
    mem.client = MagicMock()
    mem.collection_prefix = "memory_"
    mem.global_collection = "memory_global"
    return mem


# ---------------------------------------------------------------------------
# _make_document_key tests
# ---------------------------------------------------------------------------

class TestMakeDocumentKey:
    """Tests for _make_document_key (chunk → document key)."""

    def test_key_formation_global(self, memory):
        metadata = {"file": "handoff.md", "chunk_id": 2}
        key = memory._make_document_key("global", metadata)
        assert key == "[global] handoff.md"

    def test_key_formation_project(self, memory):
        metadata = {"file": "decisions.md", "chunk_id": 0}
        key = memory._make_document_key("my-project", metadata)
        assert key == "[my_project] decisions.md"

    def test_key_formation_with_dashes(self, memory):
        metadata = {"file": "architecture.md"}
        key = memory._make_document_key("my-fancy-app", metadata)
        assert key == "[my_fancy_app] architecture.md"

    def test_key_is_document_level_not_chunk(self, memory):
        metadata = {"file": "doc.md", "chunk_id": 5, "chunk_total": 10}
        key = memory._make_document_key("proj", metadata)
        assert "chunk" not in key
        assert key == "[proj] doc.md"

    def test_key_handles_missing_file(self, memory):
        metadata = {"chunk_id": 3}
        key = memory._make_document_key("src", metadata)
        assert key == "[src] unknown"


# ---------------------------------------------------------------------------
# index_directory tests (with chunking)
# ---------------------------------------------------------------------------

class TestIndexDirectory:
    """Tests for index_directory with chunking."""

    def test_index_creates_chunks_with_metadata(self, memory, tmp_path):
        """index_directory should create chunks with proper metadata."""
        collection = MagicMock()
        memory.client.get_or_create_collection.return_value = collection

        md = tmp_path / "test.md"
        md.write_text("Paragraph one.\n\nParagraph two.\n\nParagraph three.", encoding="utf-8")

        memory.index_directory(tmp_path, "memory_test")

        # Проверяем, что коллекция была создана/получена
        memory.client.get_or_create_collection.assert_called_with("memory_test")
        assert collection.upsert.called

        call_args = collection.upsert.call_args[1]
        # Должны быть ids, documents, embeddings, metadatas
        assert "ids" in call_args
        assert "documents" in call_args
        assert "embeddings" in call_args
        assert "metadatas" in call_args

        # Проверяем структуру metadata
        for meta in call_args["metadatas"]:
            assert "file" in meta
            assert "chunk_id" in meta
            assert "chunk_total" in meta
            assert meta["file"] == "test.md"

        # Все id должны содержать ':'
        for cid in call_args["ids"]:
            assert ":" in cid

    def test_index_skips_empty_directory(self, memory):
        """index_directory should handle empty directory gracefully."""
        memory.index_directory(Path("/nonexistent"), "memory_test")
        memory.client.get_or_create_collection.assert_not_called()

    def test_index_handles_unreadable_file(self, memory, tmp_path, monkeypatch):
        """index_directory should skip files that can't be read."""
        collection = MagicMock()
        memory.client.get_or_create_collection.return_value = collection

        md = tmp_path / "unreadable.md"
        md.write_text("Content", encoding="utf-8")

        # Подменяем read_text так, чтобы она выбрасывала ошибку
        def mock_read_text(*args, **kwargs):
            raise OSError("Permission denied")

        monkeypatch.setattr(Path, "read_text", mock_read_text)

        memory.index_directory(tmp_path, "memory_test")

        # Коллекция создаётся, но add не вызывается (нет чанков)
        memory.client.get_or_create_collection.assert_called_once()
        collection.upsert.assert_not_called()

    def test_index_file_with_empty_content(self, memory, tmp_path):
        """Empty file should not produce chunks."""
        collection = MagicMock()
        memory.client.get_or_create_collection.return_value = collection

        md = tmp_path / "empty.md"
        md.write_text("", encoding="utf-8")

        memory.index_directory(tmp_path, "memory_test")

        # add не должен вызываться
        collection.upsert.assert_not_called()


# ---------------------------------------------------------------------------
# search_all aggregation tests
# ---------------------------------------------------------------------------

class TestSearchAllAggregation:
    """Tests for search_all document‑level aggregation."""

    def test_aggregates_chunks_into_single_document(self, memory):
        """search_all should group multiple chunks of the same file."""
        memory.model = MagicMock()
        emb_mock = MagicMock()
        emb_mock.tolist.return_value = [0.1, 0.2]
        memory.model.encode.return_value = [emb_mock]

        fake_collection = MagicMock()
        # Возвращаем два чанка одного файла
        fake_collection.query.return_value = {
            "ids": [["doc_chunk0", "doc_chunk1"]],
            "documents": [["First chunk.", "Second chunk."]],
            "metadatas": [[
                {"file": "doc.md", "chunk_id": 0, "chunk_total": 2},
                {"file": "doc.md", "chunk_id": 1, "chunk_total": 2},
            ]],
            "distances": [[0.1, 0.3]],
        }
        memory.client.get_collection.return_value = fake_collection
        memory.client.list_collections.return_value = []
        memory.collection_prefix = "memory_"
        memory.global_collection = "memory_global"

        results = memory.search_all("test", n_results=5)
        # Должен быть один результат (документ), а не два
        assert len(results) == 1
        assert results[0]["key"] == "[global] doc.md"
        assert results[0]["distance"] == 0.1  # лучший (минимальный)
        assert "_chunks" in results[0]
        assert len(results[0]["_chunks"]) == 2

    def test_separate_documents_stay_separate(self, memory):
        """Different files should produce separate results."""
        memory.model = MagicMock()
        emb_mock = MagicMock()
        emb_mock.tolist.return_value = [0.1, 0.2]
        memory.model.encode.return_value = [emb_mock]

        fake_collection = MagicMock()
        fake_collection.query.return_value = {
            "ids": [["id1", "id2"]],
            "documents": [["Content A", "Content B"]],
            "metadatas": [[
                {"file": "file1.md", "chunk_id": 0, "chunk_total": 1},
                {"file": "file2.md", "chunk_id": 0, "chunk_total": 1},
            ]],
            "distances": [[0.1, 0.2]],
        }
        memory.client.get_collection.return_value = fake_collection
        memory.client.list_collections.return_value = []
        memory.collection_prefix = "memory_"
        memory.global_collection = "memory_global"

        results = memory.search_all("test", n_results=5)
        assert len(results) == 2
        keys = [r["key"] for r in results]
        assert "[global] file1.md" in keys
        assert "[global] file2.md" in keys