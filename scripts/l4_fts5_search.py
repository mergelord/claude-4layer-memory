#!/usr/bin/env python3
# pylint: disable=wrong-import-position, import-outside-toplevel, too-many-lines
# -*- coding: utf-8 -*-
"""
L4 FTS5 Search - Fast keyword search for memory system

Дополняет семантический поиск ChromaDB быстрым keyword-поиском через SQLite FTS5.
Поддерживает чанковую индексацию, collapse до одного лучшего чанка на документ,
и трёх-сигнальный гибридный поиск (FTS, semantic, BM25).

Использование:
    python l4_fts5_search.py init                    # Инициализация FTS5 таблицы
    python l4_fts5_search.py reindex                 # Полная переиндексация
    python l4_fts5_search.py reindex --incremental   # Инкрементальная (по mtime/size)
    python l4_fts5_search.py search "query"          # Поиск
    python l4_fts5_search.py hybrid "query"          # Гибридный поиск (sequential)
    python l4_fts5_search.py hybrid --parallel "query"  # Параллельный поиск (2-3x faster)
"""

import json
import logging
import os
import sqlite3
import subprocess
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
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
    sanitize_fts5_query,
)

# Centralized configuration (stdlib-only, safe to import eagerly).
# pylint: disable-next=wrong-import-position,import-error
from l4_config import get_config  # noqa: E402

# BM25 search (optional module)
try:
    # pylint: disable-next=wrong-import-position,import-error
    from l4_bm25_search import fetch_bm25_results  # noqa: E402
except ImportError:
    fetch_bm25_results = None


def _configure_windows_utf8_stdio() -> None:
    """Configure UTF-8 stdio for direct Windows CLI execution only.

    This must not run at import time: MCP stdio expects the original
    ``sys.stdout`` object to expose ``.buffer``. Rewrapping stdout/stderr while
    importing this module breaks ``python mcp_server.py`` on Windows before the
    MCP server can start.
    """
    if sys.platform != "win32":
        return

    import codecs

    if hasattr(sys.stdout, "buffer"):
        sys.stdout = codecs.getwriter("utf-8")(sys.stdout.buffer, "strict")
    if hasattr(sys.stderr, "buffer"):
        sys.stderr = codecs.getwriter("utf-8")(sys.stderr.buffer, "strict")


# Настройка логирования
logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")


# ---------------------------------------------------------------------------
# FTS5 query sanitization
# ---------------------------------------------------------------------------
# ``sanitize_fts5_query`` is imported from :mod:`ranking` (see the single
# source-of-truth definition there). It is shared with ``l4_bm25_search``
# so both lexical engines normalise raw user input identically. Keeping
# it in ``ranking`` (which both modules already import) avoids a circular
# import between ``l4_fts5_search`` and ``l4_bm25_search``.


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

        config = get_config()
        if db_path is None:
            db_path = config.fts5_db_path

        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self.global_memory = config.memory_dir
        self.projects_base = config.projects_dir

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

    @staticmethod
    def _ensure_meta_table(conn: sqlite3.Connection) -> None:
        """Create the per-file metadata table if it does not yet exist.

        ``memory_files`` records one row per indexed document keyed by
        ``(source, path)`` with the ``(mtime_ns, size)`` signature used by
        :meth:`reindex_incremental` to detect changes without re-reading every
        file. It is created alongside the FTS table and is safe to call
        repeatedly.
        """
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS memory_files (
                source TEXT NOT NULL,
                path TEXT NOT NULL,
                mtime_ns INTEGER NOT NULL,
                size INTEGER NOT NULL,
                chunks INTEGER NOT NULL DEFAULT 0,
                indexed_at TEXT,
                PRIMARY KEY (source, path)
            )
            """
        )

    @staticmethod
    def _file_signature(path: Path) -> Tuple[int, int]:
        """Return ``(mtime_ns, size)`` used to detect file changes."""
        stat_res = path.stat()
        return stat_res.st_mtime_ns, stat_res.st_size

    @staticmethod
    def _record_file_meta(
        conn: sqlite3.Connection,
        source: str,
        rel_path: str,
        *,
        mtime_ns: int,
        size: int,
        chunks: int,
    ) -> None:
        """Upsert the indexed-file metadata row for ``(source, rel_path)``."""
        conn.execute(
            """
            INSERT OR REPLACE INTO memory_files
                (source, path, mtime_ns, size, chunks, indexed_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                source,
                rel_path,
                mtime_ns,
                size,
                chunks,
                datetime.now(timezone.utc).isoformat(),
            ),
        )

    def _collect_memory_files(self) -> List[Tuple[Path, Path, str]]:
        """Enumerate indexable markdown files as ``(md_file, base_path, source)``.

        Mirrors the discovery logic historically inlined in ``reindex_all``:
        global memory under ``self.global_memory`` (source ``"global"``) plus
        each project's ``memory/`` directory (source = project directory name).
        Non-directories and projects without a ``memory/`` folder are skipped.
        Shared by both full and incremental reindex so they always see an
        identical file set.
        """
        files_to_index: List[Tuple[Path, Path, str]] = []

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
                    files_to_index.append(
                        (md_file, memory_path, project_dir.name)
                    )

        return files_to_index

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
                self._ensure_meta_table(conn)
                conn.commit()
                logging.info("FTS5 table initialized")
                return True
        # AUDIT #5: narrowed from a blanket ``except Exception`` to
        # ``sqlite3.Error``. Only SQLite-level failures (locked/corrupt DB,
        # malformed DDL) are expected here and degrade to ``False``; any other
        # error now propagates instead of being silently swallowed.
        except sqlite3.Error as e:
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
            mtime_ns, size = self._file_signature(md_file)

            with self._get_connection() as conn:
                self._ensure_meta_table(conn)
                for chunk in chunks:
                    conn.execute(
                        "INSERT INTO memory_fts (path, source, content) VALUES (?, ?, ?)",
                        (rel_path, source, chunk),
                    )
                self._record_file_meta(
                    conn,
                    source,
                    rel_path,
                    mtime_ns=mtime_ns,
                    size=size,
                    chunks=len(chunks),
                )
                conn.commit()
            return True
        # AUDIT #5: narrowed from a blanket ``except Exception``. File reads
        # can fail with OSError / UnicodeDecodeError and the FTS writes with
        # sqlite3.Error; those degrade to ``False`` (skip this file) while any
        # unexpected error propagates instead of being silently swallowed.
        except (OSError, UnicodeDecodeError, sqlite3.Error) as e:
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
                self._ensure_meta_table(conn)
                conn.execute("DELETE FROM memory_fts")
                conn.execute("DELETE FROM memory_files")
                conn.commit()

            files_to_index = self._collect_memory_files()

            with ThreadPoolExecutor(max_workers=4) as executor:
                futures = {
                    executor.submit(
                        self._index_single_file, md_file, base_path, source
                    ): md_file
                    for md_file, base_path, source in files_to_index
                }
                for future in as_completed(futures):
                    # Bug #3: ``_index_single_file`` already narrows its own
                    # except to the realistic failure modes and returns False,
                    # but ``future.result()`` can still raise here — e.g. an
                    # unexpected error from ``chunk_text``/splitting, or a
                    # ``CancelledError`` if the pool tears down. A single
                    # failing file must NOT abort the whole batch (previously
                    # it bubbled out and reindex silently returned 0 files
                    # with no per-file diagnosis). This is a per-task
                    # fault-isolation boundary, mirroring the per-engine
                    # boundary in cmd_hybrid_parallel's fetch_* wrappers.
                    try:
                        succeeded = future.result()
                    except Exception as e:  # noqa: BLE001
                        logging.error(
                            "Reindex worker failed for %s: %s",
                            futures[future], e,
                        )
                        continue
                    if succeeded:
                        indexed_count += 1

            logging.info("Reindexed %s files", indexed_count)
            self.clear_cache()
            return indexed_count

        # AUDIT #5: narrowed from a blanket ``except Exception`` to the
        # realistic failure modes — sqlite3.Error from the DELETE/commit and
        # OSError while walking the memory directories. Unexpected errors now
        # propagate instead of being silently swallowed.
        except (OSError, sqlite3.Error) as e:
            logging.error("Reindex failed: %s", e)
            return 0

    def reindex_incremental(self) -> dict:
        """Переиндексация только изменённых/новых/удалённых файлов.

        Compares each discoverable file's ``(mtime_ns, size)`` signature against
        the stored ``memory_files`` metadata and reindexes just the differences,
        instead of the full ``DELETE`` + rebuild performed by
        :meth:`reindex_all`. Files that disappeared from disk are removed from
        both the FTS index and the metadata table.

        Returns a summary dict with integer counts: ``added``, ``updated``,
        ``removed``, ``unchanged`` and ``indexed`` (== added + updated).
        """
        summary = {
            "added": 0,
            "updated": 0,
            "removed": 0,
            "unchanged": 0,
            "indexed": 0,
        }

        try:
            with self._get_connection() as conn:
                self._ensure_meta_table(conn)
                stored_rows = conn.execute(
                    "SELECT source, path, mtime_ns, size FROM memory_files"
                ).fetchall()

            stored = {
                (row["source"], row["path"]): (row["mtime_ns"], row["size"])
                for row in stored_rows
            }

            seen = set()
            for md_file, base_path, source in self._collect_memory_files():
                if md_file.name.startswith("."):
                    continue
                try:
                    rel_path = normalize_document_path(
                        md_file.relative_to(base_path)
                    )
                    signature = self._file_signature(md_file)
                except OSError as exc:
                    logging.warning("Skip unreadable file %s: %s", md_file, exc)
                    continue

                identity = (source, rel_path)
                seen.add(identity)
                previous = stored.get(identity)

                if previous is None:
                    if self._reindex_one_file(md_file, base_path, source):
                        summary["added"] += 1
                elif previous != signature:
                    if self._reindex_one_file(md_file, base_path, source):
                        summary["updated"] += 1
                else:
                    summary["unchanged"] += 1

            removed_identities = [key for key in stored if key not in seen]
            if removed_identities:
                with self._get_connection() as conn:
                    self._ensure_meta_table(conn)
                    for source, rel_path in removed_identities:
                        conn.execute(
                            "DELETE FROM memory_fts WHERE path = ? AND source = ?",
                            (rel_path, source),
                        )
                        conn.execute(
                            "DELETE FROM memory_files WHERE path = ? AND source = ?",
                            (rel_path, source),
                        )
                        summary["removed"] += 1
                    conn.commit()

            summary["indexed"] = summary["added"] + summary["updated"]

            if summary["indexed"] or summary["removed"]:
                self.clear_cache()

            logging.info(
                "Incremental reindex: +%d ~%d -%d =%d",
                summary["added"],
                summary["updated"],
                summary["removed"],
                summary["unchanged"],
            )
            return summary

        # AUDIT #5: same narrowing rationale as reindex_all — only the realistic
        # sqlite3.Error / OSError failure modes degrade to the (partial)
        # summary; unexpected errors propagate.
        except (OSError, sqlite3.Error) as e:
            logging.error("Incremental reindex failed: %s", e)
            return summary

    def _reindex_one_file(
        self, md_file: Path, base_path: Path, source: str
    ) -> bool:
        """Reindex a single file in place (delete old rows, insert fresh chunks).

        Unlike :meth:`_index_single_file` (full-rebuild helper that only
        inserts into a freshly cleared table), this removes any existing rows
        for the document first so it is safe to call repeatedly during
        incremental reindex, and records per-file metadata so future runs can
        detect changes by mtime/size.
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
            mtime_ns, size = self._file_signature(md_file)

            with self._get_connection() as conn:
                self._ensure_meta_table(conn)
                conn.execute(
                    "DELETE FROM memory_fts WHERE path = ? AND source = ?",
                    (rel_path, source),
                )
                for chunk in chunks:
                    conn.execute(
                        "INSERT INTO memory_fts (path, source, content) VALUES (?, ?, ?)",
                        (rel_path, source, chunk),
                    )
                self._record_file_meta(
                    conn,
                    source,
                    rel_path,
                    mtime_ns=mtime_ns,
                    size=size,
                    chunks=len(chunks),
                )
                conn.commit()
            return True
        except (OSError, UnicodeDecodeError, sqlite3.Error) as e:
            logging.warning("Failed to index %s: %s", md_file.name, e)
            return False

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
                self._ensure_meta_table(conn)
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
                mtime_ns, size = self._file_signature(file_path)
                self._record_file_meta(
                    conn,
                    source,
                    rel_path,
                    mtime_ns=mtime_ns,
                    size=size,
                    chunks=len(chunks),
                )
                conn.commit()
                logging.info(
                    "Indexed: %s (%s) with %d chunks", rel_path, source, len(chunks)
                )
                self.clear_cache()
                return True

        # AUDIT #5: narrowed from a blanket ``except Exception``. File reads
        # can raise OSError / UnicodeDecodeError and the FTS writes raise
        # sqlite3.Error; those degrade to ``False`` while any unexpected error
        # propagates instead of being silently swallowed.
        except (OSError, UnicodeDecodeError, sqlite3.Error) as e:
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
            # AUDIT #5: narrowed from a blanket ``except Exception``. Cost
            # tracking is best-effort telemetry that must never break search,
            # so only its realistic failure modes are swallowed (cost-DB
            # sqlite3.Error / OSError and CostTracker path-validation
            # ValueError); the error detail is now logged and any unexpected
            # error propagates instead of being silently swallowed.
            except (sqlite3.Error, OSError, ValueError) as exc:
                logging.debug("Cost tracking failed: %s", exc)

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
        # AUDIT #5: narrowed from a blanket ``except Exception`` to the
        # realistic failure modes — sqlite3.Error from the COUNT/GROUP BY
        # queries and OSError from the DB-size stat() — which degrade to an
        # empty-stats payload. Unexpected errors now propagate.
        except (OSError, sqlite3.Error) as e:
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


def cmd_reindex(fts: L4FTS5Search, incremental: bool = False) -> None:
    if incremental:
        summary = fts.reindex_incremental()
        print(
            "[OK] Incremental reindex: "
            f"+{summary['added']} ~{summary['updated']} "
            f"-{summary['removed']} ={summary['unchanged']} "
            f"({summary['indexed']} indexed)"
        )
    else:
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


def build_hybrid_streams(
    fts_results: list,
    semantic_results: list[dict],
    bm25_results: list[dict],
) -> Tuple[list[dict], list[dict], list[dict]]:
    """Строит и collapse'ит три сигнальных потока (1 документ = 1 сигнал).

    Единый источник правды для sequential (``cmd_hybrid``), parallel
    (``cmd_hybrid_parallel``) и runtime (``l4_hybrid_runtime.build_hybrid_results``):
    все пути строят идентичные потоки. Каждый поток помечается явным
    ``source_type``, проверяется fail-fast, затем схлопывается до одного
    лучшего чанка на документ.

    Args:
        fts_results: результаты FTS5 (``SearchResult`` с .key/.path/.snippet/.rank).
        semantic_results: сырые dict-хиты семантики.
        bm25_results: сырые dict-хиты BM25.

    Returns:
        Кортеж (fts_stream, semantic_stream, bm25_stream) после collapse.
    """
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

    return fts_stream, semantic_stream, bm25_stream


def rrf_merge_streams(
    fts_stream: list[dict],
    semantic_stream: list[dict],
    bm25_stream: list[dict],
):
    """Сливает три collapse'нутых потока через RRF и нормализует score'ы.

    Rerank сознательно НЕ применяется здесь: cross-encoder реранкинг
    остаётся ответственностью вызывающего (inline в ``cmd_hybrid`` /
    ``cmd_hybrid_parallel`` / runtime), чтобы сохранить раздельные
    тайминги Merge/Rerank и контроль enable_rerank.
    """
    return normalize_scores(
        rrf_merge(
            ("fts", fts_stream),
            ("semantic", semantic_stream),
            ("bm25", bm25_stream),
        )
    )


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

    # Функции-обертки для параллельного выполнения.
    # AUDIT #5: каждый wrapper намеренно ловит широкий ``except Exception`` —
    # это per-engine граница изоляции отказов: каждый поиск исполняется в
    # своём потоке, и падение одного движка (в т.ч. неожиданной ошибкой) не
    # должно ронять остальные движки или общий результат. Сбой логируется
    # (не глотается молча), а движок просто не даёт хитов. Поведение
    # зафиксировано тестом
    # test_cmd_hybrid_parallel_engine_failure_degrades_to_remaining_streams.
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

    fts_stream, semantic_stream, bm25_stream = build_hybrid_streams(
        fts_results, semantic_results, bm25_results
    )

    print(f"\n[HYBRID SEARCH - PARALLEL] '{query}'")
    print(f"Fetch time: {fetch_time:.3f}s (parallel execution)")
    print("=" * 70)

    if not fts_stream and not semantic_stream and not bm25_stream:
        print("No results from any engine.\n")
        return

    merge_start = time.time()
    merged = rrf_merge_streams(fts_stream, semantic_stream, bm25_stream)
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

    # BM25 (optional module).
    # AUDIT #5: широкий ``except Exception`` здесь намеренный — bm25 это
    # опциональный внешний движок, и его сбой (в т.ч. неожиданный) не должен
    # ронять гибридный поиск; ошибка логируется, а bm25 просто не участвует.
    bm25_results: list[dict] = []  # type: ignore
    if fetch_bm25_results is not None:
        try:
            bm25_results = fetch_bm25_results(query)  # type: ignore
        except Exception as exc:
            logging.warning("BM25 search failed: %s", exc)

    fts_stream, semantic_stream, bm25_stream = build_hybrid_streams(
        fts_results, semantic_results, bm25_results
    )

    print(f"\n[HYBRID SEARCH] '{query}'")
    print("=" * 70)

    if not fts_stream and not semantic_stream and not bm25_stream:
        print("No results from any engine.\n")
        return

    merged = rrf_merge_streams(fts_stream, semantic_stream, bm25_stream)

    # Опциональный cross‑encoder реранкинг
    reranker = _get_l4_rerank() if enable_rerank and merged else None
    if reranker is not None:
        merged = reranker(query, merged[:20])

    _print_merged_results(merged)


def main() -> None:
    """CLI интерфейс."""
    _configure_windows_utf8_stdio()

    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1]
    fts = L4FTS5Search()

    if command == "init":
        cmd_init(fts)
    elif command == "reindex":
        incremental = "--incremental" in sys.argv[2:]
        cmd_reindex(fts, incremental=incremental)
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
