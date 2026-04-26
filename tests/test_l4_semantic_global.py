#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unit tests for L4 Semantic Global Memory

Покрытие:
- Инициализация и конфигурация
- Нормализация имён проектов
- Валидация путей
- Индексация (глобальная и проектная)
- Поиск (глобальный, проектный, кросс-проектный)
- Batch обработка и параллелизм
- Безопасность (проверка прав доступа)
- Cleanup коллекций
"""

import json
import shutil
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.l4_semantic_global import GlobalSemanticMemory, format_distance


class TestNormalizeProjectName:
    """Test project name normalization"""

    def test_normalize_with_dashes(self):
        """Test normalization of dashes"""
        assert GlobalSemanticMemory.normalize_project_name("my-project-name") == "my_project_name"

    def test_normalize_with_spaces(self):
        """Test normalization of spaces"""
        assert GlobalSemanticMemory.normalize_project_name("project with spaces") == "project_with_spaces"

    def test_normalize_multiple_underscores(self):
        """Test collapsing multiple underscores"""
        assert GlobalSemanticMemory.normalize_project_name("my--weird__project") == "my_weird_project"

    def test_normalize_special_chars(self):
        """Test removal of special characters"""
        assert GlobalSemanticMemory.normalize_project_name("project@#$name") == "project_name"


class TestFormatDistance:
    """Test distance formatting"""

    def test_format_float(self):
        """Test formatting float distance"""
        assert format_distance(0.12345) == "0.123"

    def test_format_int(self):
        """Test formatting int distance"""
        assert format_distance(1) == "1.000"

    def test_format_none(self):
        """Test formatting None distance"""
        assert format_distance(None) == "N/A"

    def test_format_string(self):
        """Test formatting string distance"""
        assert format_distance("invalid") == "N/A"


class TestInitialization:
    """Test GlobalSemanticMemory initialization"""

    @pytest.fixture
    def temp_home(self):
        """Create temporary home directory"""
        temp_dir = Path(tempfile.mkdtemp())
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)

    @pytest.fixture
    def mock_chroma(self):
        """Mock ChromaDB"""
        with patch('scripts.l4_semantic_global.chromadb') as mock:
            mock_client = MagicMock()
            mock.PersistentClient.return_value = mock_client
            yield mock

    @pytest.fixture
    def mock_sentence_transformer(self):
        """Mock SentenceTransformer"""
        with patch('scripts.l4_semantic_global.SentenceTransformer') as mock:
            yield mock

    def test_init_default_config(self, temp_home, mock_chroma, mock_sentence_transformer):
        """Test initialization with default config"""
        with patch('pathlib.Path.home', return_value=temp_home):
            # Create required directories
            (temp_home / ".claude" / "memory").mkdir(parents=True)
            (temp_home / ".claude" / "projects").mkdir(parents=True)

            memory = GlobalSemanticMemory()

            assert memory.home == temp_home
            assert memory.global_memory == temp_home / ".claude" / "memory"
            assert memory.config == GlobalSemanticMemory.DEFAULT_CONFIG

    def test_init_with_custom_config(self, temp_home, mock_chroma, mock_sentence_transformer):
        """Test initialization with custom config"""
        with patch('pathlib.Path.home', return_value=temp_home):
            # Create directories
            (temp_home / ".claude" / "memory").mkdir(parents=True)
            (temp_home / ".claude" / "projects").mkdir(parents=True)

            # Create custom config
            config_dir = Path(__file__).parent.parent / "config"
            config_dir.mkdir(exist_ok=True)
            config_file = config_dir / "semantic_config.json"

            custom_config = {
                "embedding_model": "custom-model",
                "batch_size": 20,
                "max_workers": 8,
                "max_chunk_size": 1000,
                "search_results": {"default": 15, "global": 10, "project": 10},
                "cache_size": 256,
                "collection_names": {"global": "custom_global", "project_prefix": "custom_"}
            }

            try:
                with open(config_file, 'w', encoding='utf-8') as f:
                    json.dump(custom_config, f)

                memory = GlobalSemanticMemory()
                assert memory.config['batch_size'] == 20
                assert memory.config['max_workers'] == 8
            finally:
                if config_file.exists():
                    config_file.unlink()


class TestPathValidation:
    """Test path validation"""

    @pytest.fixture
    def temp_home(self):
        """Create temporary home directory"""
        temp_dir = Path(tempfile.mkdtemp())
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)

    @pytest.fixture
    def mock_chroma(self):
        """Mock ChromaDB"""
        with patch('scripts.l4_semantic_global.chromadb') as mock:
            mock_client = MagicMock()
            mock.PersistentClient.return_value = mock_client
            yield mock

    @pytest.fixture
    def mock_sentence_transformer(self):
        """Mock SentenceTransformer"""
        with patch('scripts.l4_semantic_global.SentenceTransformer') as mock:
            yield mock

    def test_validate_paths_success(self, temp_home, mock_chroma, mock_sentence_transformer):
        """Test successful path validation"""
        with patch('pathlib.Path.home', return_value=temp_home):
            (temp_home / ".claude" / "memory").mkdir(parents=True)
            (temp_home / ".claude" / "projects").mkdir(parents=True)

            memory = GlobalSemanticMemory()
            assert memory.home == temp_home


class TestIndexing:
    """Test indexing operations"""

    @pytest.fixture
    def temp_home(self):
        """Create temporary home directory"""
        temp_dir = Path(tempfile.mkdtemp())
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)

    @pytest.fixture
    def mock_chroma(self):
        """Mock ChromaDB"""
        with patch('scripts.l4_semantic_global.chromadb') as mock:
            mock_client = MagicMock()
            mock_collection = MagicMock()
            mock_collection.count.return_value = 0
            mock_collection.get.return_value = {"ids": []}
            mock_client.get_or_create_collection.return_value = mock_collection
            mock.PersistentClient.return_value = mock_client
            yield mock

    @pytest.fixture
    def mock_sentence_transformer(self):
        """Mock SentenceTransformer for indexing tests"""
        with patch('scripts.l4_semantic_global.SentenceTransformer') as mock:
            mock_model = MagicMock()
            # Mock encode to return object with tolist() method
            mock_result = MagicMock()
            mock_result.tolist.return_value = [[0.1, 0.2, 0.3]]
            mock_model.encode.return_value = mock_result
            mock.return_value = mock_model
            yield mock

    def test_index_global_memory_success(self, temp_home, mock_chroma, mock_sentence_transformer):
        """Test successful global memory indexing"""
        with patch('pathlib.Path.home', return_value=temp_home):
            # Create global memory with files
            memory_dir = temp_home / ".claude" / "memory"
            memory_dir.mkdir(parents=True)
            (temp_home / ".claude" / "projects").mkdir(parents=True)

            # Create test files
            (memory_dir / "test1.md").write_text("# Test 1\nContent", encoding='utf-8')
            (memory_dir / "test2.md").write_text("# Test 2\nContent", encoding='utf-8')

            memory = GlobalSemanticMemory()
            result = memory.index_global_memory()

            assert result is True

    def test_index_global_memory_not_found(self, temp_home, mock_chroma, mock_sentence_transformer):
        """Test indexing when global memory not found"""
        with patch('pathlib.Path.home', return_value=temp_home):
            (temp_home / ".claude" / "projects").mkdir(parents=True)

            memory = GlobalSemanticMemory()
            result = memory.index_global_memory()

            assert result is False

    def test_index_global_memory_no_access(self, temp_home, mock_chroma, mock_sentence_transformer):
        """Test indexing without read access"""
        with patch('pathlib.Path.home', return_value=temp_home):
            memory_dir = temp_home / ".claude" / "memory"
            memory_dir.mkdir(parents=True)
            (temp_home / ".claude" / "projects").mkdir(parents=True)

            memory = GlobalSemanticMemory()

            with patch('os.access', return_value=False):
                result = memory.index_global_memory()
                assert result is False

    def test_index_project_success(self, temp_home, mock_chroma, mock_sentence_transformer):
        """Test successful project indexing"""
        with patch('pathlib.Path.home', return_value=temp_home):
            (temp_home / ".claude" / "memory").mkdir(parents=True)
            (temp_home / ".claude" / "projects").mkdir(parents=True)

            # Create project with memory
            project_dir = temp_home / "test_project"
            memory_dir = project_dir / "memory"
            memory_dir.mkdir(parents=True)

            (memory_dir / "test.md").write_text("# Test\nContent", encoding='utf-8')

            memory = GlobalSemanticMemory()
            result = memory.index_project(project_dir)

            assert result is True

    def test_index_project_not_found(self, temp_home, mock_chroma, mock_sentence_transformer):
        """Test indexing when project memory not found"""
        with patch('pathlib.Path.home', return_value=temp_home):
            (temp_home / ".claude" / "memory").mkdir(parents=True)
            (temp_home / ".claude" / "projects").mkdir(parents=True)

            project_dir = temp_home / "test_project"
            project_dir.mkdir()

            memory = GlobalSemanticMemory()
            result = memory.index_project(project_dir)

            assert result is False


class TestSearch:
    """Test search operations"""

    @pytest.fixture
    def temp_home(self):
        """Create temporary home directory"""
        temp_dir = Path(tempfile.mkdtemp())
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)

    @pytest.fixture
    def mock_chroma(self):
        """Mock ChromaDB with search results"""
        with patch('scripts.l4_semantic_global.chromadb') as mock:
            mock_client = MagicMock()
            mock_collection = MagicMock()

            # Mock search results
            mock_collection.query.return_value = {
                'ids': [['id1', 'id2']],
                'documents': [['doc1', 'doc2']],
                'metadatas': [[{'file': 'test.md'}, {'file': 'test2.md'}]],
                'distances': [[0.1, 0.2]]
            }
            mock_collection.count.return_value = 2
            mock_collection.get.return_value = {"ids": []}

            mock_client.get_collection.return_value = mock_collection
            mock_client.get_or_create_collection.return_value = mock_collection
            mock_client.list_collections.return_value = []

            mock.PersistentClient.return_value = mock_client
            yield mock

    @pytest.fixture
    def mock_sentence_transformer(self):
        """Mock SentenceTransformer for search tests"""
        with patch('scripts.l4_semantic_global.SentenceTransformer') as mock:
            mock_model = MagicMock()
            # Mock encode to return object with tolist() method
            mock_result = MagicMock()
            mock_result.tolist.return_value = [[0.1, 0.2, 0.3]]
            mock_model.encode.return_value = mock_result
            mock.return_value = mock_model
            yield mock

    def test_search_global(self, temp_home, mock_chroma, mock_sentence_transformer):
        """Test global search"""
        with patch('pathlib.Path.home', return_value=temp_home):
            (temp_home / ".claude" / "memory").mkdir(parents=True)
            (temp_home / ".claude" / "projects").mkdir(parents=True)

            memory = GlobalSemanticMemory()
            results = memory.search_global("test query")

            assert len(results) == 2
            assert results[0]['text'] == 'doc1'
            assert results[0]['distance'] == 0.1

    def test_search_project(self, temp_home, mock_chroma, mock_sentence_transformer):
        """Test project search"""
        with patch('pathlib.Path.home', return_value=temp_home):
            (temp_home / ".claude" / "memory").mkdir(parents=True)
            (temp_home / ".claude" / "projects").mkdir(parents=True)

            memory = GlobalSemanticMemory()
            results = memory.search_project("test_project", "test query")

            assert len(results) == 2

    def test_search_all(self, temp_home, mock_chroma, mock_sentence_transformer):
        """Test cross-project search"""
        with patch('pathlib.Path.home', return_value=temp_home):
            (temp_home / ".claude" / "memory").mkdir(parents=True)
            (temp_home / ".claude" / "projects").mkdir(parents=True)

            memory = GlobalSemanticMemory()
            results = memory.search_all("test query")

            assert isinstance(results, list)


class TestCleanup:
    """Test cleanup operations"""

    @pytest.fixture
    def temp_home(self):
        """Create temporary home directory"""
        temp_dir = Path(tempfile.mkdtemp())
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)

    @pytest.fixture
    def mock_chroma(self):
        """Mock ChromaDB"""
        with patch('scripts.l4_semantic_global.chromadb') as mock:
            mock_client = MagicMock()
            mock_collection = MagicMock()
            mock_collection.count.return_value = 10
            mock_collection.get.return_value = {"ids": []}

            # Mock collections list
            mock_collection_info1 = MagicMock()
            mock_collection_info1.name = "memory_global"
            mock_collection_info2 = MagicMock()
            mock_collection_info2.name = "memory_old_project"

            mock_client.list_collections.return_value = [mock_collection_info1, mock_collection_info2]
            mock_client.get_collection.return_value = mock_collection
            mock_client.get_or_create_collection.return_value = mock_collection

            mock.PersistentClient.return_value = mock_client
            yield mock

    @pytest.fixture
    def mock_sentence_transformer(self):
        """Mock SentenceTransformer"""
        with patch('scripts.l4_semantic_global.SentenceTransformer') as mock:
            yield mock

    def test_cleanup_dry_run(self, temp_home, mock_chroma, mock_sentence_transformer):
        """Test cleanup in dry-run mode"""
        with patch('pathlib.Path.home', return_value=temp_home):
            (temp_home / ".claude" / "memory").mkdir(parents=True)
            (temp_home / ".claude" / "projects").mkdir(parents=True)

            memory = GlobalSemanticMemory()
            result = memory.cleanup_collections(dry_run=True)

            assert result['dry_run'] is True
            assert len(result['deleted']) == 0

    def test_cleanup_live(self, temp_home, mock_chroma, mock_sentence_transformer):
        """Test cleanup in live mode"""
        with patch('pathlib.Path.home', return_value=temp_home):
            (temp_home / ".claude" / "memory").mkdir(parents=True)
            (temp_home / ".claude" / "projects").mkdir(parents=True)

            memory = GlobalSemanticMemory()
            result = memory.cleanup_collections(dry_run=False)

            assert result['dry_run'] is False


class TestStats:
    """Test statistics"""

    @pytest.fixture
    def temp_home(self):
        """Create temporary home directory"""
        temp_dir = Path(tempfile.mkdtemp())
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)

    @pytest.fixture
    def mock_chroma(self):
        """Mock ChromaDB"""
        with patch('scripts.l4_semantic_global.chromadb') as mock:
            mock_client = MagicMock()
            mock_collection = MagicMock()
            mock_collection.count.return_value = 42
            mock_collection.get.return_value = {"ids": []}

            mock_collection_info = MagicMock()
            mock_collection_info.name = "memory_global"
            mock_collection_info.metadata = {"description": "Global memory"}

            mock_client.list_collections.return_value = [mock_collection_info]
            mock_client.get_collection.return_value = mock_collection
            mock_client.get_or_create_collection.return_value = mock_collection

            mock.PersistentClient.return_value = mock_client
            yield mock

    @pytest.fixture
    def mock_sentence_transformer(self):
        """Mock SentenceTransformer"""
        with patch('scripts.l4_semantic_global.SentenceTransformer') as mock:
            yield mock

    def test_stats(self, temp_home, mock_chroma, mock_sentence_transformer):
        """Test statistics collection"""
        with patch('pathlib.Path.home', return_value=temp_home):
            (temp_home / ".claude" / "memory").mkdir(parents=True)
            (temp_home / ".claude" / "projects").mkdir(parents=True)

            memory = GlobalSemanticMemory()
            stats = memory.stats()

            assert 'total_collections' in stats
            assert 'collections' in stats
            assert stats['total_collections'] == 1


class TestEdgeCases:
    """Test edge cases"""

    @pytest.fixture
    def temp_home(self):
        """Create temporary home directory"""
        temp_dir = Path(tempfile.mkdtemp())
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)

    @pytest.fixture
    def mock_chroma(self):
        """Mock ChromaDB"""
        with patch('scripts.l4_semantic_global.chromadb') as mock:
            mock_client = MagicMock()
            mock_collection = MagicMock()
            mock_collection.count.return_value = 0
            mock_collection.get.return_value = {"ids": []}
            mock_collection.query.return_value = {'ids': [[]], 'documents': [[]], 'metadatas': [[]]}
            mock_client.get_or_create_collection.return_value = mock_collection
            mock_client.get_collection.return_value = mock_collection
            mock.PersistentClient.return_value = mock_client
            yield mock

    @pytest.fixture
    def mock_sentence_transformer(self):
        """Mock SentenceTransformer for edge case tests"""
        with patch('scripts.l4_semantic_global.SentenceTransformer') as mock:
            mock_model = MagicMock()
            # Mock encode to return object with tolist() method
            mock_result = MagicMock()
            mock_result.tolist.return_value = [[0.1, 0.2, 0.3]]
            mock_model.encode.return_value = mock_result
            mock.return_value = mock_model
            yield mock

    def test_empty_search_results(self, temp_home, mock_chroma, mock_sentence_transformer):
        """Test search with no results"""
        with patch('pathlib.Path.home', return_value=temp_home):
            (temp_home / ".claude" / "memory").mkdir(parents=True)
            (temp_home / ".claude" / "projects").mkdir(parents=True)

            memory = GlobalSemanticMemory()
            results = memory.search_global("nonexistent query")

            assert results == []

    def test_unicode_in_content(self, temp_home, mock_chroma, mock_sentence_transformer):
        """Test Unicode handling"""
        with patch('pathlib.Path.home', return_value=temp_home):
            memory_dir = temp_home / ".claude" / "memory"
            memory_dir.mkdir(parents=True)
            (temp_home / ".claude" / "projects").mkdir(parents=True)

            # Create file with Unicode
            (memory_dir / "unicode.md").write_text("# Тест\nСодержимое на русском", encoding='utf-8')

            memory = GlobalSemanticMemory()
            result = memory.index_global_memory()

            assert result is True


class TestNormalizeIdPart:
    """Tests for the ASCII-safe chunk-ID component builder."""

    def test_ascii_passes_through(self):
        result = GlobalSemanticMemory._normalize_id_part("hello-world.md")
        assert result == "hello-world.md"

    def test_cyrillic_only_falls_back_to_hash(self):
        """A pure-Cyrillic stem must produce a stable non-empty ID component."""
        result = GlobalSemanticMemory._normalize_id_part("тест")
        assert result, "ID component must not be empty"
        # Same input -> same output (deterministic, hash-based fallback).
        assert result == GlobalSemanticMemory._normalize_id_part("тест")

    def test_distinct_cyrillic_inputs_produce_distinct_ids(self):
        """Two different non-ASCII names must not collide on the empty string."""
        a = GlobalSemanticMemory._normalize_id_part("файл-один")
        b = GlobalSemanticMemory._normalize_id_part("файл-два")
        assert a != b

    def test_special_chars_replaced(self):
        result = GlobalSemanticMemory._normalize_id_part("a/b\\c:d")
        assert "/" not in result
        assert "\\" not in result
        assert ":" not in result


class TestSearchInCollectionDesync:
    """_search_in_collection must tolerate truncated / mismatched Chroma payloads."""

    @pytest.fixture
    def memory(self, tmp_path):
        with patch('pathlib.Path.home', return_value=tmp_path), \
             patch('chromadb.PersistentClient'), \
             patch('scripts.l4_semantic_global.SentenceTransformer') as mock_st:
            (tmp_path / ".claude" / "memory").mkdir(parents=True)
            (tmp_path / ".claude" / "projects").mkdir(parents=True)
            mock_st.return_value.encode.return_value.tolist.return_value = [[0.1, 0.2]]
            return GlobalSemanticMemory()

    def test_clamps_to_shortest_array(self, memory):
        """If documents/metadatas are shorter than ids, clamp instead of IndexError."""
        collection = MagicMock()
        # ids has 3 entries but documents only 2 — pre-fix this would IndexError.
        collection.query.return_value = {
            'ids': [['a', 'b', 'c']],
            'documents': [['doc-a', 'doc-b']],
            'metadatas': [[{'file': 'a'}, {'file': 'b'}]],
            'distances': [[0.1, 0.2, 0.3]],
        }

        results = memory._search_in_collection(collection, "query", 3, "test")

        assert len(results) == 2
        assert [r['id'] for r in results] == ['a', 'b']

    def test_empty_results(self, memory):
        collection = MagicMock()
        collection.query.return_value = {'ids': [[]]}
        results = memory._search_in_collection(collection, "query", 5, "test")
        assert results == []

    def test_reuses_passed_query_embedding(self, memory):
        """When a pre-computed embedding is passed, the model must NOT be called again."""
        collection = MagicMock()
        collection.query.return_value = {
            'ids': [['x']],
            'documents': [['doc']],
            'metadatas': [[{}]],
            'distances': [[0.0]],
        }
        precomputed = [[0.5, 0.6]]
        memory.model.encode.reset_mock()

        memory._search_in_collection(
            collection, "query", 1, "test", query_embedding=precomputed
        )

        memory.model.encode.assert_not_called()
        collection.query.assert_called_once()
        kwargs = collection.query.call_args.kwargs
        assert kwargs['query_embeddings'] is precomputed


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
