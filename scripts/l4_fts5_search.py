#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
L4 FTS5 Search - Fast keyword search for memory system

Дополняет семантический поиск ChromaDB быстрым keyword-поиском через SQLite FTS5.
Вдохновлено CliClaw (https://github.com/a-prs/CliClaw)

Использование:
    python l4_fts5_search.py init          # Инициализация FTS5 таблицы
    python l4_fts5_search.py reindex       # Полная переиндексация
    python l4_fts5_search.py search "query" # Поиск
    python l4_fts5_search.py hybrid "query" # Гибридный поиск (FTS5 + ChromaDB)
"""

import logging
import os
import sqlite3
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import List, Optional, Tuple

# Импорт cost tracker
sys.path.insert(0, str(Path(__file__).parent))
try:
    from cost_tracker import CostTracker
    COST_TRACKING_ENABLED = True
except ImportError:
    COST_TRACKING_ENABLED = False

# Настройка UTF-8 для Windows
if sys.platform == 'win32':
    import codecs
    if hasattr(sys.stdout, 'buffer'):
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
        sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='[%(levelname)s] %(message)s'
)


@dataclass
class SearchResult:
    """Результат поиска"""
    path: str
    snippet: str
    rank: float
    source: str  # 'fts5' или 'semantic'


class L4FTS5Search:
    """FTS5 поиск для системы памяти"""

    def __init__(self, db_path: Optional[Path] = None):
        """
        Инициализация FTS5 поиска

        Args:
            db_path: Путь к SQLite БД (по умолчанию ~/.claude/memory_fts5.db)
        """
        self.home = Path.home()
        if db_path is None:
            db_path = self.home / ".claude" / "memory_fts5.db"

        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # Директории памяти
        self.global_memory = self.home / ".claude" / "memory"
        self.projects_base = self.home / ".claude" / "projects"

    def clear_cache(self):
        """Очистить кэш поиска (вызывать после reindex/index_file)"""
        self._cached_search.cache_clear()

    def _get_connection(self) -> sqlite3.Connection:
        """Получить подключение к БД"""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def init_fts(self) -> bool:
        """Создать FTS5 таблицу если не существует"""
        try:
            with self._get_connection() as conn:
                conn.execute("""
                    CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(
                        path UNINDEXED,
                        source UNINDEXED,
                        content,
                        tokenize='unicode61 remove_diacritics 2'
                    )
                """)
                conn.commit()
                logging.info("FTS5 table initialized")
                return True
        except Exception as e:
            logging.error("FTS5 initialization failed: %s", e)
            return False

    def _index_single_file(self, md_file: Path, base_path: Path, source: str) -> bool:
        """
        Индексировать один файл (helper для параллельной обработки)

        Args:
            md_file: Путь к файлу
            base_path: Базовый путь для относительного пути
            source: Источник (global или имя проекта)

        Returns:
            True если успешно
        """
        if md_file.name.startswith('.'):
            return False

        # Проверка прав доступа
        if not os.access(md_file, os.R_OK):
            logging.warning("No read access: %s", md_file)
            return False

        try:
            content = md_file.read_text(encoding='utf-8')
            rel_path = str(md_file.relative_to(base_path))

            with self._get_connection() as conn:
                conn.execute(
                    "INSERT INTO memory_fts (path, source, content) VALUES (?, ?, ?)",
                    (rel_path, source, content)
                )
                conn.commit()
            return True
        except Exception as e:
            logging.warning("Failed to index %s: %s", md_file.name, e)
            return False

    def reindex_all(self) -> int:
        """
        Полная переиндексация всех файлов памяти с параллельной обработкой

        Returns:
            Количество проиндексированных файлов
        """
        indexed_count = 0

        try:
            with self._get_connection() as conn:
                # Очистка старых данных
                conn.execute("DELETE FROM memory_fts")
                conn.commit()

            # Собираем все файлы для индексации
            files_to_index = []

            # Глобальная память
            if self.global_memory.exists():
                for md_file in self.global_memory.rglob("*.md"):
                    files_to_index.append((md_file, self.global_memory, "global"))

            # Проектная память
            if self.projects_base.exists():
                for project_dir in self.projects_base.iterdir():
                    if not project_dir.is_dir():
                        continue

                    memory_path = project_dir / "memory"
                    if not memory_path.exists():
                        continue

                    for md_file in memory_path.rglob("*.md"):
                        files_to_index.append((md_file, memory_path, project_dir.name))

            # Параллельная индексация
            with ThreadPoolExecutor(max_workers=4) as executor:
                futures = {
                    executor.submit(self._index_single_file, md_file, base_path, source): md_file
                    for md_file, base_path, source in files_to_index
                }

                for future in as_completed(futures):
                    if future.result():
                        indexed_count += 1

            logging.info("Reindexed %s files", indexed_count)
            self.clear_cache()  # Инвалидация кэша после переиндексации
            return indexed_count

        except Exception as e:
            logging.error("Reindex failed: %s", e)
            return 0

    def index_file(self, file_path: Path, source: str) -> bool:
        """
        Индексировать один файл

        Args:
            file_path: Путь к файлу
            source: Источник (global или имя проекта)

        Returns:
            True если успешно
        """
        # Проверка прав доступа
        if not os.access(file_path, os.R_OK):
            logging.error("No read access: %s", file_path)
            return False

        try:
            with self._get_connection() as conn:
                content = file_path.read_text(encoding='utf-8')
                rel_path = file_path.name

                # Удалить старую запись
                conn.execute(
                    "DELETE FROM memory_fts WHERE path = ? AND source = ?",
                    (rel_path, source)
                )

                # Добавить новую
                conn.execute(
                    "INSERT INTO memory_fts (path, source, content) VALUES (?, ?, ?)",
                    (rel_path, source, content)
                )
                conn.commit()
                logging.info("Indexed: %s (%s)", rel_path, source)
                self.clear_cache()  # Инвалидация кэша после индексации
                return True

        except Exception as e:
            logging.error("Failed to index %s: %s", file_path, e)
            return False

    @lru_cache(maxsize=128)
    def _cached_search(self, query: str, limit: int) -> Tuple[SearchResult, ...]:
        """
        Кэшируемая версия поиска (внутренний метод)

        Args:
            query: Поисковый запрос
            limit: Максимум результатов

        Returns:
            Tuple результатов (immutable для кэширования)
        """
        try:
            with self._get_connection() as conn:
                rows = conn.execute(
                    """
                    SELECT
                        path,
                        source,
                        snippet(memory_fts, 2, '»', '«', '...', 60) as snippet,
                        rank
                    FROM memory_fts
                    WHERE memory_fts MATCH ?
                    ORDER BY rank
                    LIMIT ?
                    """,
                    (query, limit)
                ).fetchall()

                results = tuple(
                    SearchResult(
                        path=f"[{row['source']}] {row['path']}",
                        snippet=row['snippet'],
                        rank=row['rank'],
                        source='fts5'
                    )
                    for row in rows
                )

                return results

        except Exception as e:
            logging.error("Cached search failed: %s", e)
            return tuple()

    def search(self, query: str, limit: int = 10) -> List[SearchResult]:
        """
        FTS5 поиск с ранжированием и кэшированием

        Args:
            query: Поисковый запрос
            limit: Максимум результатов

        Returns:
            Список результатов поиска
        """
        # Используем кэшируемую версию
        results = list(self._cached_search(query, limit))

        # Отслеживаем стоимость операции
        if COST_TRACKING_ENABLED and results:
            try:
                tracker = CostTracker()
                # FTS5 - локальный поиск, минимальная стоимость
                input_tokens = len(query.split()) * 1.3
                output_tokens = sum(len(r.snippet.split()) for r in results) * 1.3
                tracker.track_operation(
                    operation_type='fts5_search',
                    input_tokens=int(input_tokens),
                    output_tokens=int(output_tokens),
                    model='embedding',
                    metadata=f"results: {len(results)}"
                )
            except Exception as e:  # nosec B110
                logging.debug("Cost tracking failed: %s", e)

        return results

    def stats(self) -> dict:
        """Статистика FTS5 индекса"""
        try:
            with self._get_connection() as conn:
                row = conn.execute(
                    "SELECT COUNT(*) as count FROM memory_fts"
                ).fetchone()

                sources = conn.execute(
                    "SELECT source, COUNT(*) as count FROM memory_fts GROUP BY source"
                ).fetchall()

                return {
                    'total_documents': row['count'],
                    'sources': {s['source']: s['count'] for s in sources},
                    'db_path': str(self.db_path),
                    'db_size_kb': round(self.db_path.stat().st_size / 1024, 1) if self.db_path.exists() else 0
                }
        except Exception as e:
            logging.error("Stats failed: %s", e)
            return {
                'total_documents': 0,
                'sources': {},
                'db_path': str(self.db_path),
                'db_size_kb': 0
            }



def cmd_init(fts: L4FTS5Search):
    """Обработчик команды init"""
    if fts.init_fts():
        print("[OK] FTS5 table initialized")
    else:
        print("[ERROR] Initialization failed")
        sys.exit(1)


def cmd_reindex(fts: L4FTS5Search):
    """Обработчик команды reindex"""
    count = fts.reindex_all()
    print(f"[OK] Reindexed {count} files")


def cmd_search(fts: L4FTS5Search, query: str):
    """Обработчик команды search"""
    results = fts.search(query)
    print(f"\n[SEARCH] FTS5 Search: '{query}'")
    print(f"Found {len(results)} results\n")

    for i, result in enumerate(results, 1):
        print(f"[{i}] {result.path} (rank: {result.rank:.3f})")
        print(f"    {result.snippet}")
        print()


def cmd_stats(fts: L4FTS5Search):
    """Обработчик команды stats"""
    stats = fts.stats()
    print("\n[STATS] FTS5 Statistics:")
    print(f"   Total documents: {stats['total_documents']}")
    print(f"   DB size: {stats['db_size_kb']} KB")
    print(f"   DB path: {stats['db_path']}")
    print("\n   Sources:")
    for source, count in stats['sources'].items():
        print(f"      {source}: {count} documents")


def cmd_hybrid(fts: L4FTS5Search, query: str):
    """Обработчик команды hybrid"""
    import subprocess

    fts_results = fts.search(query, limit=5)

    try:
        semantic_script = Path(__file__).parent / "l4_semantic_global.py"

        if semantic_script.exists():
            result = subprocess.run(
                [sys.executable, str(semantic_script), "search-all", query],
                capture_output=True,
                text=True,
                timeout=30,
                check=False
            )

            print(f"\n[HYBRID SEARCH] '{query}'")
            print("=" * 70)

            print("\n[FTS5 Results - Keyword Match]")
            print("-" * 70)
            if fts_results:
                for i, res in enumerate(fts_results, 1):
                    print(f"[{i}] {res.path} (rank: {res.rank:.3f})")
                    print(f"    {res.snippet}")
                    print()
            else:
                print("No FTS5 results found\n")

            print("\n[Semantic Results - Meaning Match]")
            print("-" * 70)
            if result.returncode == 0:
                print(result.stdout)
            else:
                print("Semantic search failed or not available\n")
        else:
            print("[WARN] l4_semantic_global.py not found")
            print("       Falling back to FTS5 only")

            for i, res in enumerate(fts_results, 1):
                print(f"[{i}] {res.path} (rank: {res.rank:.3f})")
                print(f"    {res.snippet}")
                print()

    except Exception as e:
        logging.error("Hybrid search failed: %s", e)
        print("[ERROR] Hybrid search failed, showing FTS5 results only:")
        for i, res in enumerate(fts_results, 1):
            print(f"[{i}] {res.path} (rank: {res.rank:.3f})")
            print(f"    {res.snippet}")
            print()


def main():
    """CLI интерфейс"""
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1]
    fts = L4FTS5Search()

    if command == 'init':
        cmd_init(fts)

    elif command == 'reindex':
        cmd_reindex(fts)

    elif command == 'search':
        if len(sys.argv) < 3:
            print("Usage: l4_fts5_search.py search <query>")
            sys.exit(1)
        query = ' '.join(sys.argv[2:])
        cmd_search(fts, query)

    elif command == 'stats':
        cmd_stats(fts)

    elif command == 'hybrid':
        if len(sys.argv) < 3:
            print("Usage: l4_fts5_search.py hybrid <query>")
            sys.exit(1)
        query = ' '.join(sys.argv[2:])
        cmd_hybrid(fts, query)

    else:
        print(f"Unknown command: {command}")
        print(__doc__)
        sys.exit(1)


if __name__ == '__main__':
    main()
