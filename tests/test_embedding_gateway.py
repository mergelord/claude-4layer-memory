#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Тесты для Embedding Gateway (P1)."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

# Мокаем внешние библиотеки, чтобы избежать импорта реальных моделей
sys.modules['sentence_transformers'] = MagicMock()
sys.modules['chromadb'] = MagicMock()
sys.modules['chromadb.config'] = MagicMock()

from l4_semantic_global import GlobalSemanticMemory


class TestEmbeddingGateway:
    """Проверяем, что все поисковые запросы проходят через _encode_query."""

    def test_search_all_uses_gateway(self):
        """search_all должен вызывать _encode_query, а не model.encode напрямую."""
        memory = GlobalSemanticMemory.__new__(GlobalSemanticMemory)
        
        # Мокаем модель
        memory.model = MagicMock()
        fake_embedding = MagicMock()
        fake_embedding.tolist.return_value = [0.1, 0.2, 0.3]
        memory.model.encode.return_value = [fake_embedding]
        
        # Мокаем клиент Chroma
        memory.client = MagicMock()
        fake_collection = MagicMock()
        fake_collection.query.return_value = {
            'ids': [['id1']],
            'documents': [['content']],
            'metadatas': [[{'file': 'test.md'}]],
            'distances': [[0.5]]
        }
        memory.client.get_collection.return_value = fake_collection
        
        # Настраиваем конфигурацию
        memory.config = {
            'collection_names': {
                'global': 'test_global',
                'project_prefix': 'test_'
            }
        }
        memory.client.list_collections.return_value = []
        memory.collection_prefix = 'test_'
        memory.global_collection = 'test_global'

        # Вызываем поиск
        results = memory.search_all("test query", n_results=3)

        # Проверяем, что model.encode вызван ровно 1 раз (через _encode_query)
        assert memory.model.encode.call_count == 1, (
            f"Expected 1 call to model.encode, got {memory.model.encode.call_count}"
        )

    def test_repeated_query_uses_cache(self):
        """Повторный запрос должен использовать кэш, не вызывая модель повторно."""
        memory = GlobalSemanticMemory.__new__(GlobalSemanticMemory)
        memory.model = MagicMock()
        fake_embedding = MagicMock()
        fake_embedding.tolist.return_value = [0.1, 0.2]
        memory.model.encode.return_value = [fake_embedding]
        
        # Вызываем _encode_query напрямую
        memory._encode_query("test")
        memory._encode_query("test")
        
        # Модель должна быть вызвана только один раз
        assert memory.model.encode.call_count == 1