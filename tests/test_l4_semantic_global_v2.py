#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Тесты для L4 Semantic Global Memory (v2) с чанкингом и адаптерным слоем."""

import sys
from pathlib import Path
from unittest.mock import MagicMock

# Мокаем sentence-transformers и chromadb ДО импорта нашего модуля
sys.modules['sentence_transformers'] = MagicMock()
sys.modules['chromadb'] = MagicMock()
sys.modules['chromadb.config'] = MagicMock()

# Добавляем путь к scripts перед импортом
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from l4_semantic_global import GlobalSemanticMemory  # noqa: E402
from chunking import chunk_text  # noqa: E402


# -------------------------------------------------------------------
# Chunking unit tests (используем chunk_text из chunking)
# -------------------------------------------------------------------

class TestChunking:
    """Tests for chunk_text function."""

    def test_small_text_returns_one_chunk(self):
        text = "Short paragraph."
        chunks = chunk_text(text, max_chars=200)
        assert len(chunks) == 1
        assert chunks[0] == text.strip()

    def test_paragraph_split(self):
        text = "A" * 100 + "\n\n" + "B" * 100 + "\n\n" + "C" * 100
        chunks = chunk_text(text, max_chars=250)
        assert 2 <= len(chunks) <= 3
        combined = " ".join(chunks)
        assert "A" * 100 in combined
        assert "B" * 100 in combined
        assert "C" * 100 in combined

    def test_long_paragraph_split_by_sentences(self):
        sent = "Sentence {}."
        para = " ".join(sent.format(i) for i in range(10))
        chunks = chunk_text(para, max_chars=50)
        assert len(chunks) > 1

    def test_empty_text_yields_empty_string(self):
        chunks = chunk_text("", max_chars=100)
        assert len(chunks) == 0

    def test_overlap_inclusion(self):
        text = "ParagraphOne\n\nParagraphTwo\n\nParagraphThree\n\nParagraphFour\n\nParagraphFive"
        chunks = chunk_text(text, max_chars=20, overlap_paragraphs=2)
        assert len(chunks) > 1, "Should split into several chunks"


# -------------------------------------------------------------------
# Adapter layer tests
# -------------------------------------------------------------------

class TestDocumentAdapter:
    """Tests for _make_document_key (chunk → document key)."""

    def test_key_formation_global(self):
        memory = GlobalSemanticMemory.__new__(GlobalSemanticMemory)
        metadata = {"file": "handoff.md", "chunk_id": 2}
        key = memory._make_document_key("global", metadata)
        assert key == "[global] handoff.md"

    def test_key_formation_project(self):
        memory = GlobalSemanticMemory.__new__(GlobalSemanticMemory)
        metadata = {"file": "decisions.md", "chunk_id": 0}
        key = memory._make_document_key("my-project", metadata)
        assert key == "[my_project] decisions.md"

    def test_key_is_document_level_not_chunk(self):
        memory = GlobalSemanticMemory.__new__(GlobalSemanticMemory)
        metadata = {"file": "doc.md", "chunk_id": 5}
        key = memory._make_document_key("proj", metadata)
        assert "chunk" not in key
        assert key == "[proj] doc.md"


# -------------------------------------------------------------------
# Indexing with chunks tests
# -------------------------------------------------------------------

class TestIndexDirectory:
    """Tests for index_directory with chunking."""

    def test_index_creates_chunks(self, tmp_path):
        memory = GlobalSemanticMemory.__new__(GlobalSemanticMemory)
        memory.client = MagicMock()
        memory.collection_prefix = "memory_"
        model = MagicMock()
        emb_mock = MagicMock()
        emb_mock.tolist.return_value = [0.1, 0.2]
        model.encode.return_value = [emb_mock]
        memory.model = model

        md = tmp_path / "test.md"
        md.write_text("Para 1.\n\nPara 2.\n\nPara 3.", encoding="utf-8")

        memory.index_directory(tmp_path, "memory_test")

        memory.client.get_or_create_collection.assert_called_with("memory_test")
        collection = memory.client.get_or_create_collection.return_value
        assert collection.add.called
        call_args = collection.add.call_args[1]
        for cid in call_args['ids']:
            assert ":" in cid
        for meta in call_args['metadatas']:
            assert "file" in meta
            assert "chunk_id" in meta
            assert "chunk_total" in meta
        filenames = {m['file'] for m in call_args['metadatas']}
        assert filenames == {"test.md"}


# -------------------------------------------------------------------
# Search output tests
# -------------------------------------------------------------------

class TestSearchAllOutput:
    """Tests for search_all – verifies document-level key and aggregation."""

    def test_search_returns_document_level_key(self):
        memory = GlobalSemanticMemory.__new__(GlobalSemanticMemory)
        memory.model = MagicMock()
        emb_mock = MagicMock()
        emb_mock.tolist.return_value = [0.1, 0.2]
        memory.model.encode.return_value = [emb_mock]
        memory.client = MagicMock()

        fake_collection = MagicMock()
        fake_collection.query.return_value = {
            'ids': [['id_chunk0', 'id_chunk1']],
            'documents': [['chunk A', 'chunk B']],
            'metadatas': [[
                {'file': 'doc.md', 'chunk_id': 0, 'chunk_total': 2},
                {'file': 'doc.md', 'chunk_id': 1, 'chunk_total': 2}
            ]],
            'distances': [[0.1, 0.3]]
        }
        memory.client.get_collection.return_value = fake_collection
        memory.client.list_collections.return_value = []
        memory.collection_prefix = "memory_"
        memory.global_collection = "memory_global"

        results = memory.search_all("test", n_results=5)
        assert len(results) == 1
        result = results[0]
        assert result['key'] == "[global] doc.md"
        assert result['distance'] == 0.1
        assert '_chunks' in result
        assert len(result['_chunks']) == 2

    def test_search_different_documents_produce_separate_results(self):
        memory = GlobalSemanticMemory.__new__(GlobalSemanticMemory)
        memory.model = MagicMock()
        emb_mock = MagicMock()
        emb_mock.tolist.return_value = [0.1, 0.2]
        memory.model.encode.return_value = [emb_mock]
        memory.client = MagicMock()

        fake_collection = MagicMock()
        fake_collection.query.return_value = {
            'ids': [['id1', 'id2']],
            'documents': [['doc A', 'doc B']],
            'metadatas': [[
                {'file': 'file1.md', 'chunk_id': 0, 'chunk_total': 1},
                {'file': 'file2.md', 'chunk_id': 0, 'chunk_total': 1}
            ]],
            'distances': [[0.1, 0.2]]
        }
        memory.client.get_collection.return_value = fake_collection
        memory.client.list_collections.return_value = []
        memory.collection_prefix = "memory_"
        memory.global_collection = "memory_global"

        results = memory.search_all("test", n_results=5)
        assert len(results) == 2
        keys = [r['key'] for r in results]
        assert "[global] file1.md" in keys
        assert "[global] file2.md" in keys


# -------------------------------------------------------------------
# Original encode tests
# -------------------------------------------------------------------

class TestEncode:
    def test_encode_returns_list_of_floats(self):
        memory = GlobalSemanticMemory.__new__(GlobalSemanticMemory)
        memory.model = MagicMock()
        emb_mock = MagicMock()
        emb_mock.tolist.return_value = [0.1, 0.2, 0.3]
        memory.model.encode.return_value = [emb_mock]
        result = memory._encode_query("test")
        assert result == [0.1, 0.2, 0.3]

    def test_encode_is_cached(self):
        memory = GlobalSemanticMemory.__new__(GlobalSemanticMemory)
        memory.model = MagicMock()
        emb_mock = MagicMock()
        emb_mock.tolist.return_value = [0.1, 0.2]
        memory.model.encode.return_value = [emb_mock]
        r1 = memory._encode_query("test")
        r2 = memory._encode_query("test")
        assert r1 == r2
        assert memory.model.encode.call_count == 1
