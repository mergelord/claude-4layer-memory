#!/usr/bin/env python3
# pylint: disable=wrong-import-position, import-outside-toplevel
# -*- coding: utf-8 -*-
"""
L4 FTS5 Search - Fast keyword search for memory system

Дополняет семантический поиск ChromaDB быстрым keyword-поиском через SQLite FTS5.
Поддерживает чанковую индексацию, collapse до одного лучшего чанка на документ,
и трёх-сигнальный гибридный поиск (FTS, semantic, BM25).

Использование:
    python l4_fts5_search.py init                    # Инициализация FTS5 таблицы
    python l4_fts5_search.py reindex                 # Полная переиндексация
    python l4_fts5_search.py search "query"          # Поиск
    python l4_fts5_search.py hybrid "query"          # Гибридный поиск (sequential)
    python l4_fts5_search.py hybrid --parallel "query"  # Параллельный поиск (2-3x faster)
"""

import json
import logging
import os
import re
import sqlite3
import subprocess
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterator, List, Optional, Tuple

# Импорт cost tracker
sys.path.insert(0, str(Path(__file__).parent))
try:
    from cost_tracker import CostTracker

    COST_TRACKING_ENABLED = True
except ImportError:
    COST_TRACKING_ENABLED = False

# Common chunker (shared with semantic module)
# pylint: disable-next=wrong-import-position,import-error
from chunking import chunk_text  # noqa: E402

# RRF ranker is local + stdlib-only, safe to import eagerly.
# pylint: disable-next=wrong-import-position,import-error
from ranking import (  # noqa: E402
    make_join_key,
    normalize_document_path,
    normalize_existing_key,
    normalize_scores,
    rrf_merge,
)

# BM25 search (optional module)
try:
    # pylint: disable-next=wrong-import-position,import-error
    from l4_bm25_search import fetch_bm25_results  # noqa: E402
except ImportError:
    fetch_bm25_results = None

# Настройка UTF-8 для Windows
if sys.platform == "win32":
    import codecs

    if hasattr(sys.stdout, "buffer"):
        sys.stdout = codecs.getwriter("utf-8")(sys.stdout.buffer, "strict")
        sys.stderr = codecs.getwriter("utf-8")(sys.stderr.buffer, "strict")

# Настройка логирования
logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")


# ---------------------------------------------------------------------------
# FTS5 query sanitization
# ---------------------------------------------------------------------------

# Токены-слова из произвольного пользовательского ввода. \w в Python 3 по
# умолчанию Unicode-aware, поэтому кириллица и другие алфавиты сохраняются.
_FTS5_TOKEN_RE = re.compile(r"\w+", re.UNICODE)


def sanitize_fts5_query(query: str) -> str:
    """Преобразует сырой пользовательский ввод в безопасный FTS5 MATCH-запрос.

    FTS5 трактует ряд символов как синтаксис запроса: двойные кавычки,
    ``*``, ``:``, ``^``, ``-``, ``(`` / ``)``, а также ключевые слова
    ``AND`` / ``OR`` / ``NOT`` / ``NEAR``. Из-за этого сырой ввод вроде
    ``C++``, ``the "bug"`` или ``foo:bar`` приводит к
    ``sqlite3.OperationalError``.

    Мы извлекаем из запроса только токены-слова и оборачиваем каждый в
    двойные кавычки, превращая его в литеральную фразу. Токены соединяются
    пробелом (неявный AND в FTS5). Поскольку токены содержат только
    word-символы, любые спецсимволы и операторы FTS5 нейтрализуются.

    Возвращает пустую строку, если во вводе нет ни одного значимого токена;
    вызывающий код в этом случае должен вернуть пустой результат, не
    выполняя MATCH.
    """
    tokens = _FTS5_TOKEN_RE.findall(query)
    if not tokens:
        return ""
    return " ".join(f'"{token}"' for token in tokens)


@lru_cache(maxsize=1)
def _get_l4_rerank():
    """Import the optional cross-encoder reranker only when hybrid needs it."""
    try:
        # pylint: disable-next=import-outside-toplevel,import-error
        from l4_rerank import rerank
    except ImportError:
        return None
    return rerank


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class SearchResult:
    """Результат поиска.

    Attributes:
        path: Display path of the form ``"[source] rel_path"`` (preserves
            subdirectory information for human-readable output).
        key: Document-level join key produced by
            :func:`ranking.make_join_key`. **Must** be used for RRF
            merging across engines (FTS / BM25 / semantic) so that the
            same document is always identified by the same string,
            regardless of which engine produced the hit.
        snippet: FTS5 ``snippet()`` excerpt with delimiters.
        rank: Raw FTS5 ``rank`` value (lower == better).
        source: Retrieval method identifier (``'fts5'`` here).
    """

    path: str
    key: str
    snippet: str
    rank: float
    source: str  # 'fts5' или 'semantic' или 'bm25'


class L4FTS5Search:
    """FTS5 поиск для системы памяти"""

    def __init__(self, db_path: Optional[Path] = None) -> None:
        self.home = Path.home()
        if db_path is None:
            db_path = self.home / ".claude" / "memory_fts5.db"

        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self.global_memory = self.home / ".claude" / "memory"
        self.projects_base = self.home / ".claude" / "projects"

        # Per-instance search cache, created lazily on first use (see
        # _cached_search). Storing the lru_cache on the instance — instead of
        # decorating the method — keeps the cache scoped to this instance and
        # lets it be garbage-collected together with the instance. Decorating
        # an instance method with @lru_cache stores ``self`` in a cache that
        # lives on the class object, which pins every instance in memory and
        # shares cache entries across unrelated instances.
        self._search_cache: Any = None

    def clear_cache(self) -> None:
        """Очистить кэш поиска (вызывать после reindex/index_file)"""
        cache = getattr(self, "_search_cache", None)
        if cache is not None:
            cache.cache_clear()

    @contextmanager
    def _get_connection(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(str(self.db_path), timeout=30)
        conn.row_factory = sqlite3.Row
        try:
            try:
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA busy_timeout=30000")
                conn.execute("PRAGMA synchronous=NORMAL")
            except sqlite3.OperationalError:  # nosec
                pass
            yield conn
        finally:
            conn.close()

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
        except Exception as e:  # nosec
            logging.error("FTS5 initialization failed: %s", e)
            return False

    def _index_single_file(self, md_file: Path, base_path: Path, source: str) -> bool:
        """
        Индексировать один файл, разбивая его на чанки.
        Все чанки получают одинаковый path (для группировки в RRF),
        но разное содержимое (content).
        """
        if md_file.name.startswith("."):
            return False

        if not os.access(md_file, os.R_OK):
            logging.warning("No read access: %s", md_file)
            return False

        try:
            content = md_file.read_text(encoding="utf-8")
            rel_path = normalize_document_path(md_file.relative_to(base_path))
            chunks = chunk_text(content)

            with self._get_connection() as conn:
                for chunk in chunks:
                    conn.execute(
                        "INSERT INTO memory_fts (path, source, content) VALUES (?, ?, ?)",
                        (rel_path, source, chunk),
                    )
                conn.commit()
            return True
        except Exception as e:  # nosec
            logging.warning("Failed to index %s: %s", md_file.name, e)
            return False

    def reindex_all(self) -> int:
        """
        Полная переиндексация всех файлов памяти с параллельной обработкой.
        Каждый файл разбивается на чанки и индексируется.
        """
        indexed_count = 0

        try:
            with self._get_connection() as conn:
                conn.execute("DELETE FROM memory_fts")
                conn.commit()

            files_to_index = []

            if self.global_memory.exists():
                for md_file in self.global_memory.rglob("*.md"):
                    files_to_index.append((md_file, self.global_memory, "global"))

            if self.projects_base.exists():
                for project_dir in self.projects_base.iterdir():
                    if not project_dir.is_dir():
                        continue
                    memory_path = project_dir / "memory"
                    if not memory_path.exists():
                        continue
                    for md_file in memory_path.rglob("*.md"):
                        files_to_index.append((md_file, memory_path, project_dir.name))

            with ThreadPoolExecutor(max_workers=4) as executor:
                futures = {
                    executor.submit(
                        self._index_single_file, md_file, base_path, source
                    ): md_file
                    for md_file, base_path, source in files_to_index
                }
                for future in as_completed(futures):
                    if future.result():
                        indexed_count += 1

            logging.info("Reindexed %s files", indexed_count)
            self.clear_cache()
            return indexed_count

        except Exception as e:  # nosec
            logging.error("Reindex failed: %s", e)
            return 0

    def index_file(
        self,
        file_path: Path,
        source: str,
        base_path: Optional[Path] = None,
    ) -> bool:
        """
        Индексировать один файл (с разбивкой на чанки).
        Удаляет все предыдущие записи для этого файла и вставляет чанки.

        Когда ``base_path`` задан, ``path`` в FTS5 — POSIX rel_path
        относительно корня source-директории (это нужно чтобы
        ``archive/notes.md`` и ``current/notes.md`` оставались
        различимыми после RRF merge). Без ``base_path`` сохраняется
        старое поведение (``file_path.name``) — для обратной
        совместимости с потенциальными внешними caller'ами.
        """
        if not os.access(file_path, os.R_OK):
            logging.error("No read access: %s", file_path)
            return False

        try:
            with self._get_connection() as conn:
                content = file_path.read_text(encoding="utf-8")
                if base_path is not None:
                    rel_path = normalize_document_path(
                        file_path.relative_to(base_path)
                    )
                else:
                    rel_path = file_path.name
                conn.execute(
                    "DELETE FROM memory_fts WHERE path = ? AND source = ?",
                    (rel_path, source),
                )
                chunks = chunk_text(content)
                for chunk in chunks:
                    conn.execute(
                        "INSERT INTO memory_fts (path, source, content) VALUES (?, ?, ?)",
                        (rel_path, source, chunk),
                    )
                conn.commit()
                logging.info(
                    "Indexed: %s (%s) with %d chunks", rel_path, source, len(chunks)
                )
                self.clear_cache()
                return True

        except Exception as e:  # nosec
            logging.error("Failed to index %s: %s", file_path, e)
            return False

    def _cached_search(self, query: str, limit: int) -> Tuple[SearchResult, ...]:
        """Кэшируемый поиск (per-instance LRU).

        Кэш создаётся лениво при первом вызове и хранится на экземпляре
        (``self._search_cache``), поэтому собирается GC вместе с экземпляром и
        не шарится между разными экземплярами. Работает и для экземпляров,
        созданных в обход ``__init__`` (например, через ``__new__`` в тестах).
        """
        cache = getattr(self, "_search_cache", None)
        if cache is None:
            cache = lru_cache(maxsize=128)(self._cached_search_impl)
            self._search_cache = cache
        return cache(query, limit)

    def _cached_search_impl(self, query: str, limit: int) -> Tuple[SearchResult, ...]:
        """
        Реальная реализация поиска (вызывается через ``self._cached_search``).
        Возвращает результаты для каждого чанка,
        путь имеет вид "[source] rel_path" (без чанк-суффикса).
        """
        match_query = sanitize_fts5_query(query)
        if not match_query:
            return tuple()

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
                    (match_query, limit),
                ).fetchall()

                results = tuple(
                    SearchResult(
                        path=f"[{row['source']}] {row['path']}",
                        key=make_join_key(row['source'], row['path']),
                        snippet=row["snippet"],
                        rank=row["rank"],
                        source="fts5",
                    )
                    for row in rows
                )
                return results

        # AUDIT #5 (first slice): narrowed from a blanket ``except Exception``
        # to ``sqlite3.Error``. Only SQLite-level failures (malformed MATCH,
        # locked/corrupt DB) are expected here and degrade gracefully to an
        # empty result; any non-SQLite error (e.g. a programming bug) now
        # propagates instead of being silently swallowed.
        except sqlite3.Error as e:
            logging.error("Cached search failed: %s", e)
            return tuple()

    def search(self, query: str, limit: int = 10) -> List[SearchResult]:
        """
        FTS5 поиск с ранжированием и кэшированием.
        """
        results = list(self._cached_search(query, limit))

        if COST_TRACKING_ENABLED and results:
            try:
                tracker = CostTracker()
                input_tokens = len(query.split()) * 1.3
                output_tokens = sum(len(r.snippet.split()) for r in results) * 1.3
                tracker.track_operation(
                    operation_type="fts5_search",
                    input_tokens=int(input_tokens),
                    output_tokens=int(output_tokens),
                    model="embedding",
                    metadata=f"results: {len(results)}",
                )
            except Exception:  # nosec
                logging.debug("Cost tracking failed")

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
                    "total_documents": row["count"],
                    "sources": {s["source"]: s["count"] for s in sources},
                    "db_path": str(self.db_path),
                    "db_size_kb": (
                        round(self.db_path.stat().st_size / 1024, 1)
                        if self.db_path.exists()
                        else 0
                    ),
                }
        except Exception as e:  # nosec
            logging.error("Stats failed: %s", e)
            return {
                "total_documents": 0,
                "sources": {},
                "db_path": str(self.db_path),
                "db_size_kb": 0,
            }


# ---------------------------------------------------------------------------
# CLI commands (basic)
# ---------------------------------------------------------------------------


def cmd_init(fts: L4FTS5Search) -> None:
    if fts.init_fts():
        print("[OK] FTS5 table initialized")
    else:
        print("[ERROR] Initialization failed")
        sys.exit(1)


def cmd_reindex(fts: L4FTS5Search) -> None:
    count = fts.reindex_all()
    print(f"[OK] Reindexed {count} files")


def cmd_search(fts: L4FTS5Search, query: str) -> None:
    results = fts.search(query)
    print(f"\n[SEARCH] FTS5 Search: '{query}'")
    print(f"Found {len(results)} results\n")
    for i, result in enumerate(results, 1):
        print(f"[{i}] {result.path} (rank: {result.rank:.3f})")
        print(f"    {result.snippet}")
        print()


def cmd_stats(fts: L4FTS5Search) -> None:
    stats = fts.stats()
    print("\n[STATS] FTS5 Statistics:")
    print(f"   Total documents: {stats['total_documents']}")
    print(f"   DB size: {stats['db_size_kb']} KB")
    print(f"   DB path: {stats['db_path']}")
    print("\n   Sources:")
    for source, count in stats["sources"].items():
        print(f"      {source}: {count} documents")


# ---------------------------------------------------------------------------
# Helper: fetch semantic results via subprocess
# ---------------------------------------------------------------------------


def _fetch_semantic_results(query: str, timeout: int = 30) -> list[dict]:
    """Запускает семантический поиск и возвращает результаты в JSON."""
    semantic_script = Path(__file__).parent / "l4_semantic_global.py"
    if not semantic_script.exists():
        return []

    try:
        result = subprocess.run(
            [sys.executable, str(semantic_script), "search-all", query, "--json"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        logging.warning("Semantic search subprocess failed: %s", exc)
        return []

    if result.returncode != 0:
        logging.warning(
            "Semantic search exited %s: %s",
            result.returncode,
            result.stderr.strip(),
        )
        return []

    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        logging.warning("Semantic JSON parse failed: %s", exc)
        return []

    return payload.get("results", []) if isinstance(payload, dict) else []


# ---------------------------------------------------------------------------
# Chunk / source management helpers
# ---------------------------------------------------------------------------


def limit_chunks(stream: list[dict], max_chunks: int) -> list[dict]:
    """Ограничить количество чанков на документ (debug tool)."""
    grouped: dict[str, list[dict]] = defaultdict(list)
    for item in stream:
        grouped[item["key"]].append(item)
    limited: list[dict] = []
    for items in grouped.values():
        if "distance" in items[0]:
            items_sorted = sorted(items, key=lambda x: x.get("distance", 999))
        else:
            items_sorted = sorted(items, key=lambda x: x.get("rank", 999))
        limited.extend(items_sorted[:max_chunks])
    return limited


def collapse_to_best_per_doc(stream: list[dict]) -> list[dict]:
    """
    Оставляет ОДИН лучший чанк на каждый документ.

    Правило выбора лучшего зависит от source_type:
    - 'semantic' → минимальное distance
    - 'bm25'    → минимальный rank (порядок в выдаче)
    - 'fts'     → минимальный rank
    """
    grouped: dict[str, list[dict]] = defaultdict(list)
    for item in stream:
        grouped[item["key"]].append(item)

    collapsed: list[dict] = []
    for key, items in grouped.items():
        source_type = items[0].get("source_type")
        if not source_type:
            logging.warning("Missing source_type for key=%s, defaulting to 'fts'", key)
            source_type = "fts"

        if source_type == "semantic":
            best = min(items, key=lambda x: x.get("distance", 999))
        elif source_type == "bm25":
            best = min(items, key=lambda x: x.get("rank", 999))
        else:  # fts
            best = min(items, key=lambda x: x.get("rank", 999))

        collapsed.append(best)
    return collapsed


# ---------------------------------------------------------------------------
# Hybrid search (FTS + semantic + BM25)
# ---------------------------------------------------------------------------


def _print_source_hit(source_name: str, hit: dict) -> None:
    """Print a single hit from a source in hybrid output."""
    rank = hit.get("rank", "?")
    contrib = hit.get("rrf_contribution", 0.0)
    if source_name == "fts":
        extra = hit.get("snippet", "").strip().replace("\n", " ")[:120]
        print(f"    [{source_name} rank={rank} rrf={contrib:.4f}] {extra}")
    elif source_name == "bm25":
        score = hit.get("bm25_score", None)
        extra = hit.get("snippet", "").strip().replace("\n", " ")[:120]
        if score is not None:
            print(
                f"    [{source_name} rank={rank} rrf={contrib:.4f} score={score:.4f}] {extra}"
            )
        else:
            print(f"    [{source_name} rank={rank} rrf={contrib:.4f}] {extra}")
    else:
        distance = hit.get("distance")
        distance_str = (
            f"{distance:.3f}" if isinstance(distance, (int, float)) else "n/a"
        )
        text = hit.get("text", "").strip().replace("\n", " ")[:120]
        print(
            f"    [{source_name} rank={rank} rrf={contrib:.4f} dist={distance_str}] {text}"
        )


def _print_merged_results(merged) -> None:
    """Форматирует и выводит объединённые результаты гибридного поиска."""
    print(f"\nMerged {len(merged)} unique result(s)")
    print("-" * 70)

    for i, entry in enumerate(merged[:10], 1):
        contributors = sorted(entry.sources.keys())
        print(
            f"[{i}] {entry.key}  "
            f"score={entry.score:.4f}  "
            f"normalized={entry.normalized_score:.3f}  "
            f"sources=[{', '.join(contributors)}]"
        )
        for source_name in contributors:
            for hit in entry.sources[source_name]:
                _print_source_hit(source_name, hit)
        print()


def _validate_stream_source_type(
    stream: list[dict], expected: str, stream_name: str
) -> None:
    """Validate that all items in stream have correct source_type."""
    for i, item in enumerate(stream):
        if item.get("source_type") != expected:
            raise ValueError(
                f"{stream_name} stream item [{i}] has source_type="
                f"{item.get('source_type')!r}, expected {expected!r}"
            )


def cmd_hybrid_parallel(fts: L4FTS5Search, query: str, enable_rerank: bool = True) -> None:
    """
    Параллельный гибридный поиск: FTS5 + семантика + BM25 через ThreadPoolExecutor.
    Все источники выполняются параллельно для максимальной производительности.
    После слияния применяется опциональный cross-encoder реранкинг.

    Performance: ~2-3x faster than sequential cmd_hybrid()
    """
    import time
    start_time = time.time()

    # Функции-обертки для параллельного выполнения
    def fetch_fts():
        try:
            return fts.search(query, limit=20)
        except Exception as exc:
            logging.error("FTS search failed: %s", exc)
            return []

    def fetch_semantic():
        try:
            return _fetch_semantic_results(query)
        except Exception as exc:
            logging.error("Semantic search failed: %s", exc)
            return []

    def fetch_bm25():
        if fetch_bm25_results is None:
            return []
        try:
            return fetch_bm25_results(query)  # type: ignore
        except Exception as exc:
            logging.warning("BM25 search failed: %s", exc)
            return []

    # Параллельное выполнение всех трех поисков
    with ThreadPoolExecutor(max_workers=3) as executor:
        future_fts = executor.submit(fetch_fts)
        future_semantic = executor.submit(fetch_semantic)
        future_bm25 = executor.submit(fetch_bm25)

        # Ждем завершения всех задач
        fts_results = future_fts.result()
        semantic_results = future_semantic.result()
        bm25_results = future_bm25.result()

    fetch_time = time.time() - start_time

    # Формируем потоки с явным source_type
    fts_stream = [
        {
            "key": res.key,
            "display_path": res.path,
            "snippet": res.snippet,
            "rank": res.rank,
            "source_type": "fts",
        }
        for res in fts_results
    ]

    semantic_stream = [
        {
            **hit,
            "key": normalize_existing_key(hit.get("key", "")),
            "source_type": "semantic",
        }
        for hit in semantic_results
    ]

    bm25_stream = [
        {
            "key": normalize_existing_key(item["key"]),
            "snippet": item["snippet"],
            "rank": item.get("rank", 0),
            "bm25_score": item.get("bm25_score"),
            "source_type": "bm25",
        }
        for item in bm25_results
    ]

    # Инварианты (fail-fast вместо assert)
    _validate_stream_source_type(fts_stream, "fts", "FTS")
    _validate_stream_source_type(semantic_stream, "semantic", "Semantic")
    _validate_stream_source_type(bm25_stream, "bm25", "BM25")

    # 1 документ = 1 сигнал
    fts_stream = collapse_to_best_per_doc(fts_stream)
    semantic_stream = collapse_to_best_per_doc(semantic_stream)
    bm25_stream = collapse_to_best_per_doc(bm25_stream)

    print(f"\n[HYBRID SEARCH - PARALLEL] '{query}'")
    print(f"Fetch time: {fetch_time:.3f}s (parallel execution)")
    print("=" * 70)

    if not fts_stream and not semantic_stream and not bm25_stream:
        print("No results from any engine.\n")
        return

    merge_start = time.time()
    merged = normalize_scores(
        rrf_merge(
            ("fts", fts_stream), ("semantic", semantic_stream), ("bm25", bm25_stream)
        )
    )
    merge_time = time.time() - merge_start

    # Опциональный cross‑encoder реранкинг
    rerank_time = 0.0
    reranker = _get_l4_rerank() if enable_rerank and merged else None
    if reranker is not None:
        rerank_start = time.time()
        merged = reranker(query, merged[:20])
        rerank_time = time.time() - rerank_start

    total_time = time.time() - start_time
    print(f"Merge time: {merge_time:.3f}s")
    if rerank_time > 0:
        print(f"Rerank time: {rerank_time:.3f}s")
    print(f"Total time: {total_time:.3f}s")
    print()

    _print_merged_results(merged)


def cmd_hybrid(fts: L4FTS5Search, query: str, enable_rerank: bool = True) -> None:
    """
    Гибридный поиск: FTS5 + семантика + BM25 через Reciprocal Rank Fusion.
    Все источники независимы, каждый даёт ровно 1 сигнал на документ.
    После слияния применяется опциональный cross-encoder реранкинг.
    """
    fts_results = fts.search(query, limit=20)
    semantic_results = _fetch_semantic_results(query)

    # BM25 (optional module)
    bm25_results: list[dict] = []  # type: ignore
    if fetch_bm25_results is not None:
        try:
            bm25_results = fetch_bm25_results(query)  # type: ignore
        except Exception as exc:
            logging.warning("BM25 search failed: %s", exc)

    # Формируем потоки с явным source_type
    fts_stream = [
        {
            "key": res.key,
            "display_path": res.path,
            "snippet": res.snippet,
            "rank": res.rank,
            "source_type": "fts",
        }
        for res in fts_results
    ]

    semantic_stream = [
        {
            **hit,
            "key": normalize_existing_key(hit.get("key", "")),
            "source_type": "semantic",
        }
        for hit in semantic_results
    ]

    bm25_stream = [
        {
            "key": normalize_existing_key(item["key"]),
            "snippet": item["snippet"],
            "rank": item.get("rank", 0),
            "bm25_score": item.get("bm25_score"),
            "source_type": "bm25",
        }
        for item in bm25_results
    ]

    # Инварианты (fail-fast вместо assert)
    _validate_stream_source_type(fts_stream, "fts", "FTS")
    _validate_stream_source_type(semantic_stream, "semantic", "Semantic")
    _validate_stream_source_type(bm25_stream, "bm25", "BM25")

    # 1 документ = 1 сигнал
    fts_stream = collapse_to_best_per_doc(fts_stream)
    semantic_stream = collapse_to_best_per_doc(semantic_stream)
    bm25_stream = collapse_to_best_per_doc(bm25_stream)

    print(f"\n[HYBRID SEARCH] '{query}'")
    print("=" * 70)

    if not fts_stream and not semantic_stream and not bm25_stream:
        print("No results from any engine.\n")
        return

    merged = normalize_scores(
        rrf_merge(
            ("fts", fts_stream), ("semantic", semantic_stream), ("bm25", bm25_stream)
        )
    )

    # Опциональный cross‑encoder реранкинг
    reranker = _get_l4_rerank() if enable_rerank and merged else None
    if reranker is not None:
        merged = reranker(query, merged[:20])

    _print_merged_results(merged)


def main() -> None:
    """CLI интерфейс."""
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1]
    fts = L4FTS5Search()

    if command == "init":
        cmd_init(fts)
    elif command == "reindex":
        cmd_reindex(fts)
    elif command == "search":
        if len(sys.argv) < 3:
            print("Usage: l4_fts5_search.py search <query>")
            sys.exit(1)
        query = " ".join(sys.argv[2:])
        cmd_search(fts, query)
    elif command == "stats":
        cmd_stats(fts)
    elif command == "hybrid":
        if len(sys.argv) < 3:
            print("Usage: l4_fts5_search.py hybrid [--parallel] [--no-rerank] <query>")
            sys.exit(1)

        # Parse flags
        enable_rerank = True
        use_parallel = False
        args = sys.argv[2:]

        if "--parallel" in args:
            use_parallel = True
            args.remove("--parallel")

        if "--no-rerank" in args:
            enable_rerank = False
            args.remove("--no-rerank")

        if not args:
            print("Usage: l4_fts5_search.py hybrid [--parallel] [--no-rerank] <query>")
            sys.exit(1)

        query = " ".join(args)

        if use_parallel:
            cmd_hybrid_parallel(fts, query, enable_rerank=enable_rerank)
        else:
            cmd_hybrid(fts, query, enable_rerank=enable_rerank)
    else:
        print(f"Unknown command: {command}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
