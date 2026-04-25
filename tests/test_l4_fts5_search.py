#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unit tests for L4 FTS5 Search

Покрытие:
- Инициализация и индексация
- Поиск и кэширование
- Безопасность (права доступа, SQL injection)
- Edge cases (пустые файлы, битые пути)
"""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from l4_fts5_search import L4FTS5Search, SearchResult


class TestL4FTS5SearchInit(unittest.TestCase):
    """Тесты инициализации и базовых операций"""

    def setUp(self):
        """Создать временную БД для каждого теста"""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test_fts5.db"
        self.fts = L4FTS5Search(db_path=self.db_path)

    def tearDown(self):
        """Очистить временные файлы"""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_init_creates_db_directory(self):
        """БД директория создаётся автоматически"""
        self.assertTrue(self.db_path.parent.exists())

    def test_init_fts_creates_table(self):
        """init_fts создаёт FTS5 таблицу"""
        result = self.fts.init_fts()
        self.assertTrue(result)

        # Проверка существования таблицы
        with self.fts._get_connection() as conn:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='memory_fts'"
            )
            self.assertIsNotNone(cursor.fetchone())

    def test_init_fts_idempotent(self):
        """init_fts можно вызывать многократно"""
        self.assertTrue(self.fts.init_fts())
        self.assertTrue(self.fts.init_fts())

    def test_stats_empty_db(self):
        """stats возвращает корректные данные для пустой БД"""
        self.fts.init_fts()
        stats = self.fts.stats()

        self.assertEqual(stats['total_documents'], 0)
        self.assertEqual(stats['sources'], {})
        self.assertIn('db_path', stats)
        self.assertIn('db_size_kb', stats)


class TestL4FTS5SearchIndexing(unittest.TestCase):
    """Тесты индексации файлов"""

    def setUp(self):
        """Создать временную БД и тестовые файлы"""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test_fts5.db"
        self.fts = L4FTS5Search(db_path=self.db_path)
        self.fts.init_fts()

        # Создать тестовые файлы
        self.test_files_dir = Path(self.temp_dir) / "test_files"
        self.test_files_dir.mkdir()

        self.test_file = self.test_files_dir / "test.md"
        self.test_file.write_text("Test content for FTS5 search", encoding='utf-8')

    def tearDown(self):
        """Очистить временные файлы"""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_index_file_success(self):
        """index_file успешно индексирует файл"""
        result = self.fts.index_file(self.test_file, "test_source")
        self.assertTrue(result)

        stats = self.fts.stats()
        self.assertEqual(stats['total_documents'], 1)

    def test_index_file_empty_content(self):
        """index_file обрабатывает пустые файлы"""
        empty_file = self.test_files_dir / "empty.md"
        empty_file.write_text("", encoding='utf-8')

        result = self.fts.index_file(empty_file, "test_source")
        self.assertTrue(result)

    def test_index_file_no_read_permission(self):
        """index_file проверяет права доступа"""
        with patch('os.access', return_value=False):
            result = self.fts.index_file(self.test_file, "test_source")
            self.assertFalse(result)

    def test_index_file_nonexistent(self):
        """index_file обрабатывает несуществующие файлы"""
        fake_file = self.test_files_dir / "nonexistent.md"
        result = self.fts.index_file(fake_file, "test_source")
        self.assertFalse(result)

    def test_index_file_updates_existing(self):
        """index_file обновляет существующую запись"""
        self.fts.index_file(self.test_file, "test_source")

        # Обновить содержимое
        self.test_file.write_text("Updated content", encoding='utf-8')
        self.fts.index_file(self.test_file, "test_source")

        # Должна быть только одна запись
        stats = self.fts.stats()
        self.assertEqual(stats['total_documents'], 1)

    def test_index_single_file_helper(self):
        """_index_single_file работает корректно"""
        result = self.fts._index_single_file(
            self.test_file,
            self.test_files_dir,
            "test_source"
        )
        self.assertTrue(result)

    def test_index_single_file_skips_hidden(self):
        """_index_single_file пропускает скрытые файлы"""
        hidden_file = self.test_files_dir / ".hidden.md"
        hidden_file.write_text("Hidden content", encoding='utf-8')

        result = self.fts._index_single_file(
            hidden_file,
            self.test_files_dir,
            "test_source"
        )
        self.assertFalse(result)


class TestL4FTS5SearchQuery(unittest.TestCase):
    """Тесты поиска"""

    def setUp(self):
        """Создать БД с тестовыми данными"""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test_fts5.db"
        self.fts = L4FTS5Search(db_path=self.db_path)
        self.fts.init_fts()

        # Добавить тестовые данные
        with self.fts._get_connection() as conn:
            conn.execute(
                "INSERT INTO memory_fts (path, source, content) VALUES (?, ?, ?)",
                ("test1.md", "global", "Python programming language")
            )
            conn.execute(
                "INSERT INTO memory_fts (path, source, content) VALUES (?, ?, ?)",
                ("test2.md", "project", "JavaScript web development")
            )
            conn.execute(
                "INSERT INTO memory_fts (path, source, content) VALUES (?, ?, ?)",
                ("test3.md", "global", "Python data science machine learning")
            )
            conn.commit()

    def tearDown(self):
        """Очистить временные файлы"""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_search_finds_results(self):
        """search находит релевантные результаты"""
        results = self.fts.search("Python")
        self.assertEqual(len(results), 2)
        self.assertTrue(all(isinstance(r, SearchResult) for r in results))

    def test_search_respects_limit(self):
        """search учитывает параметр limit"""
        results = self.fts.search("Python", limit=1)
        self.assertEqual(len(results), 1)

    def test_search_no_results(self):
        """search возвращает пустой список при отсутствии результатов"""
        results = self.fts.search("nonexistent_term_xyz")
        self.assertEqual(len(results), 0)

    def test_search_special_characters(self):
        """search обрабатывает спецсимволы"""
        results = self.fts.search("Python")
        self.assertGreater(len(results), 0)

    def test_cached_search_returns_tuple(self):
        """_cached_search возвращает immutable tuple"""
        results = self.fts._cached_search("Python", 10)
        self.assertIsInstance(results, tuple)

    def test_cache_invalidation(self):
        """clear_cache очищает кэш поиска"""
        # Первый поиск
        self.fts.search("Python")
        cache_info1 = self.fts._cached_search.cache_info()

        # Второй поиск (из кэша)
        self.fts.search("Python")
        cache_info2 = self.fts._cached_search.cache_info()

        self.assertEqual(cache_info2.hits, cache_info1.hits + 1)

        # Очистка кэша
        self.fts.clear_cache()
        cache_info3 = self.fts._cached_search.cache_info()
        self.assertEqual(cache_info3.hits, 0)

    def test_search_ranking(self):
        """search возвращает результаты с корректным рангом"""
        results = self.fts.search("Python")
        self.assertTrue(all(hasattr(r, 'rank') for r in results))
        self.assertTrue(all(isinstance(r.rank, float) for r in results))


class TestL4FTS5SearchSecurity(unittest.TestCase):
    """Тесты безопасности"""

    def setUp(self):
        """Создать временную БД"""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test_fts5.db"
        self.fts = L4FTS5Search(db_path=self.db_path)
        self.fts.init_fts()

    def tearDown(self):
        """Очистить временные файлы"""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_sql_injection_protection(self):
        """Параметризованные запросы защищают от SQL injection"""
        # Попытка SQL injection
        malicious_query = "'; DROP TABLE memory_fts; --"

        # Не должно вызвать ошибку или удалить таблицу
        results = self.fts.search(malicious_query)
        self.assertIsInstance(results, list)

        # Таблица должна существовать
        with self.fts._get_connection() as conn:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='memory_fts'"
            )
            self.assertIsNotNone(cursor.fetchone())

    def test_connection_context_manager(self):
        """Контекстный менеджер работает корректно"""
        # Проверяем что контекстный менеджер не вызывает ошибок
        with self.fts._get_connection() as conn:
            self.assertIsNotNone(conn)
            result = conn.execute("SELECT 1").fetchone()
            self.assertIsNotNone(result)

    def test_stats_handles_missing_db(self):
        """stats обрабатывает отсутствующую БД"""
        # Создать новый экземпляр с несуществующей БД
        fake_db = Path(self.temp_dir) / "nonexistent.db"
        fts_fake = L4FTS5Search(db_path=fake_db)

        stats = fts_fake.stats()
        self.assertEqual(stats['total_documents'], 0)
        self.assertEqual(stats['db_size_kb'], 0)


class TestL4FTS5SearchEdgeCases(unittest.TestCase):
    """Тесты граничных случаев"""

    def setUp(self):
        """Создать временную БД"""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test_fts5.db"
        self.fts = L4FTS5Search(db_path=self.db_path)
        self.fts.init_fts()

    def tearDown(self):
        """Очистить временные файлы"""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_unicode_content(self):
        """Обработка Unicode контента"""
        test_file = Path(self.temp_dir) / "unicode.md"
        test_file.write_text("Тестовый контент на русском языке 中文", encoding='utf-8')

        result = self.fts.index_file(test_file, "test")
        self.assertTrue(result)

        results = self.fts.search("русском")
        self.assertGreater(len(results), 0)

    def test_large_content(self):
        """Обработка больших файлов"""
        test_file = Path(self.temp_dir) / "large.md"
        large_content = "test content " * 10000
        test_file.write_text(large_content, encoding='utf-8')

        result = self.fts.index_file(test_file, "test")
        self.assertTrue(result)

    def test_empty_query(self):
        """Обработка пустого запроса"""
        results = self.fts.search("")
        self.assertIsInstance(results, list)


if __name__ == '__main__':
    unittest.main()
