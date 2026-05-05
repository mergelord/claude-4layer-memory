#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Тесты для нового L4 Semantic Global Memory (v2)."""

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

# Мокаем sentence-transformers и chromadb ДО импорта нашего модуля
sys.modules['sentence_transformers'] = MagicMock()
sys.modules['chromadb'] = MagicMock()
sys.modules['chromadb.config'] = MagicMock()

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from l4_semantic_global import GlobalSemanticMemory


class TestEncode:
    """Тесты кэширования эмбеддингов."""

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


class TestSearchAll:
    """Тесты основного поиска."""

    def test_search_all_returns_results(self):
        memory = GlobalSemanticMemory.__new__(GlobalSemanticMemory)
        memory.model = MagicMock()
        emb_mock = MagicMock()
        emb_mock.tolist.return_value = [0.1, 0.2]
        memory.model.encode.return_value = [emb_mock]
        memory.client = MagicMock()
        fake_collection = MagicMock()
        fake_collection.query.return_value = {
            'ids': [['id1', 'id2']],
            'documents': [['doc1', 'doc2']],
            'metadatas': [[{'file': 'test.md'}, {'file': 'test2.md'}]],
            'distances': [[0.1, 0.2]]
        }
        memory.client.get_collection.return_value = fake_collection
        memory.client.list_collections.return_value = []
        memory.collection_prefix = "memory_"
        memory.global_collection = "memory_global"

        results = memory.search_all("query", n_results=5)
        assert len(results) == 2
        assert results[0]['id'] == 'id1'
        assert results[0]['distance'] == 0.1

    def test_search_all_dedups_by_id(self):
        memory = GlobalSemanticMemory.__new__(GlobalSemanticMemory)
        memory.model = MagicMock()
        emb_mock = MagicMock()
        emb_mock.tolist.return_value = [0.1, 0.2]
        memory.model.encode.return_value = [emb_mock]
        memory.client = MagicMock()
        fake_collection = MagicMock()
        fake_collection.query.return_value = {
            'ids': [['id1']],
            'documents': [['doc1']],
            'metadatas': [[{'file': 'test.md'}]],
            'distances': [[0.1]]
        }
        memory.client.get_collection.return_value = fake_collection
        from collections import namedtuple
        CollInfo = namedtuple('CollInfo', ['name'])
        memory.client.list_collections.return_value = [
            CollInfo('memory_global'),
            CollInfo('memory_project1')
        ]
        memory.collection_prefix = "memory_"
        memory.global_collection = "memory_global"

        results = memory.search_all("query", n_results=5)
        assert len(results) == 1
        assert results[0]['id'] == 'id1'