#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Тесты для L4 Semantic Global Memory (v2) с чанкингом и адаптерным слоем."""

import io
import sys
from pathlib import Path
from unittest.mock import MagicMock

# Мокаем sentence-transformers и chromadb ДО импорта нашего модуля
sys.modules['sentence_transformers'] = MagicMock()
sys.modules['chromadb'] = MagicMock()
sys.modules['chromadb.config'] = MagicMock()

# Добавляем путь к scripts перед импортом
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import l4_semantic_global  # noqa: E402
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
        assert collection.upsert.called
        call_args = collection.upsert.call_args[1]
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

    def test_search_global_returns_key_field(self):
        memory = GlobalSemanticMemory.__new__(GlobalSemanticMemory)
        memory.model = MagicMock()
        emb_mock = MagicMock()
        emb_mock.tolist.return_value = [0.1, 0.2]
        memory.model.encode.return_value = [emb_mock]
        memory.client = MagicMock()
        memory.collection_prefix = "memory_"
        memory.global_collection = "memory_global"

        fake_collection = MagicMock()
        fake_collection.query.return_value = {
            "ids": [["id1"]],
            "documents": [["global note"]],
            "metadatas": [[{"file": "file.md"}]],
            "distances": [[0.2]],
        }
        memory.client.get_collection.return_value = fake_collection

        results = memory.search_global("test")

        assert results[0]["key"] == "[global] file.md"

    def test_search_project_normalizes_collection_name_prefix(self):
        memory = GlobalSemanticMemory.__new__(GlobalSemanticMemory)
        memory.model = MagicMock()
        emb_mock = MagicMock()
        emb_mock.tolist.return_value = [0.1, 0.2]
        memory.model.encode.return_value = [emb_mock]
        memory.collection_prefix = "memory_"
        memory.global_collection = "memory_global"

        target_collection = MagicMock()
        target_collection.query.return_value = {
            "ids": [["id1"]],
            "documents": [["project note"]],
            "metadatas": [[{"file": "handoff.md"}]],
            "distances": [[0.1]],
        }
        listed_collection = MagicMock()
        listed_collection.name = "memory_C__BAT_CUSTOMWGMSFS"
        memory.client = MagicMock()

        def get_collection(name):
            if name == "memory_C__BAT_CUSTOMWGMSFS":
                return target_collection
            raise ValueError(name)

        memory.client.get_collection.side_effect = get_collection
        memory.client.list_collections.return_value = [listed_collection]

        results = memory.search_project("C--BAT", "handoff")

        memory.client.get_collection.assert_any_call("memory_C__BAT_CUSTOMWGMSFS")
        assert results[0]["source"] == "C__BAT_CUSTOMWGMSFS"
        assert results[0]["key"] == "[C_BAT_CUSTOMWGMSFS] handoff.md"

    def test_print_results_json_handles_raw_chunk_without_key(self, capsys):
        results = [
            {
                "text": "unicode: memory",
                "distance": 0.1,
                "metadata": {"file": "handoff.md"},
                "source": "global",
            }
        ]

        l4_semantic_global._print_results(results, json_output=True)

        assert '"key": "[global] handoff.md"' in capsys.readouterr().out


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


class TestLazyModelAndEncoding:
    def test_init_does_not_load_sentence_transformer(self):
        memory = GlobalSemanticMemory()

        assert memory._model is None

    def test_search_triggers_model_load(self):
        memory = GlobalSemanticMemory.__new__(GlobalSemanticMemory)
        memory.model_name = "test-model"
        memory._model = None
        memory.client = MagicMock()
        memory.collection_prefix = "memory_"
        memory.global_collection = "memory_global"

        fake_model = MagicMock()
        emb_mock = MagicMock()
        emb_mock.tolist.return_value = [0.1, 0.2]
        fake_model.encode.return_value = [emb_mock]
        sentence_transformer = MagicMock(return_value=fake_model)
        sys.modules["sentence_transformers"].SentenceTransformer = sentence_transformer

        fake_collection = MagicMock()
        fake_collection.query.return_value = {
            "ids": [[]],
            "documents": [[]],
            "metadatas": [[]],
            "distances": [[]],
        }
        memory.client.get_collection.return_value = fake_collection
        memory.client.list_collections.return_value = []

        memory.search_all("test")

        sentence_transformer.assert_called_once_with("test-model")
        fake_model.encode.assert_called_once()

    def test_configure_utf8_output_reconfigures_windows_streams(self, monkeypatch):
        class FakeStream:
            encoding = "cp1252"

            def __init__(self):
                self.buffer = io.BytesIO()
                self.calls = []

            def reconfigure(self, **kwargs):
                self.calls.append(kwargs)
                self.encoding = kwargs["encoding"]

        stdout = FakeStream()
        stderr = FakeStream()
        monkeypatch.setattr(l4_semantic_global.sys, "platform", "win32")
        monkeypatch.setattr(l4_semantic_global.sys, "stdout", stdout)
        monkeypatch.setattr(l4_semantic_global.sys, "stderr", stderr)

        l4_semantic_global.configure_utf8_output()

        assert stdout.encoding == "utf-8"
        assert stderr.encoding == "utf-8"

    def test_configure_utf8_output_falls_back_to_buffer(self, monkeypatch):
        class FakeStream:
            encoding = "cp1252"

            def __init__(self):
                self.buffer = io.BytesIO()

            def reconfigure(self, **kwargs):
                raise OSError("reconfigure unavailable")

        stdout = FakeStream()
        stderr = FakeStream()
        monkeypatch.setattr(l4_semantic_global.sys, "platform", "win32")
        monkeypatch.setattr(l4_semantic_global.sys, "stdout", stdout)
        monkeypatch.setattr(l4_semantic_global.sys, "stderr", stderr)

        l4_semantic_global.configure_utf8_output()

        l4_semantic_global.sys.stdout.write("память")
        l4_semantic_global.sys.stdout.flush()
        l4_semantic_global.sys.stderr.write("ошибка")
        l4_semantic_global.sys.stderr.flush()

        assert stdout.buffer.getvalue() == "память".encode("utf-8")
        assert stderr.buffer.getvalue() == "ошибка".encode("utf-8")
