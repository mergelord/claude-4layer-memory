#!/usr/bin/env python3
# pylint: disable=duplicate-code
# -*- coding: utf-8 -*-
"""
L4 BM25 Search – независимый лексический источник для гибридного поиска.

Использует функцию bm25() встроенного FTS5-движка SQLite.
Возвращает результаты в контракте, ожидаемом RRF-слиянием.

Контракт возвращаемых результатов:
- key: document-level идентификатор "[source] filename"
- rank: позиция в выдаче BM25 (1-based, чем меньше тем лучше)
- bm25_score: сырое значение BM25 (чем ближе к 0, тем лучше)
- snippet: фрагмент текста с контекстом совпадения
- source_type: "bm25" (retrieval method identifier, not original document source)
"""

import logging
import sqlite3
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, List, TypedDict

# Ensure sibling modules in scripts/ are importable when invoked as a script.
_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

# pylint: disable-next=wrong-import-position,import-error
from ranking import make_join_key, sanitize_fts5_query  # noqa: E402

# Safe FTS5 query sanitization — single source of truth, imported from
# :mod:`ranking` (shared with ``l4_fts5_search``).  Extracts \w+ tokens and
# double-quotes each, neutralising all FTS5 syntax (*, :, ^, -, AND, OR,
# NOT, NEAR, quotes, parens).  No circular import: neither lexical engine
# imports the sanitizer from the other; the shared copy lives in ranking.
# Alias kept for backward compatibility; internal callers may still use it.
_sanitize_query = sanitize_fts5_query

# Параметры snippet() функции FTS5
SNIPPET_COLUMN = 2  # Индекс колонки content в FTS таблице
SNIPPET_START_MARKER = '»'
SNIPPET_END_MARKER = '«'
SNIPPET_ELLIPSIS = '...'
SNIPPET_MAX_TOKENS = 60  # Максимум токенов в snippet


# ---------------------------------------------------------------------------
# Типы для улучшения контракта (mypy‑friendly)
# ---------------------------------------------------------------------------
class BM25Result(TypedDict):
    """Структура одного результата BM25‑поиска. Все поля обязательны."""
    key: str
    rank: int
    bm25_score: float
    snippet: str
    source_type: str


# ---------------------------------------------------------------------------
# Подключение к FTS5 БД
# ---------------------------------------------------------------------------
@contextmanager
def _get_fts5_connection() -> Iterator[sqlite3.Connection]:
    """Получить подключение к FTS5 БД (без зависимости от L4FTS5Search)."""
    db_path = Path.home() / ".claude" / "memory_fts5.db"
    conn = sqlite3.connect(str(db_path), timeout=30)
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


# ---------------------------------------------------------------------------
# Основная функция поиска
# ---------------------------------------------------------------------------
def fetch_bm25_results(query: str, limit: int = 20) -> List[BM25Result]:
    """
    Возвращает список результатов BM25-поиска, готовых для подачи в RRF.

    Использует встроенную функцию bm25() в SQLite FTS5 для ранжирования.
    BM25 scores отрицательные — чем ближе к 0, тем релевантнее документ.

    Args:
        query: Поисковый запрос (свободный текст; нормализуется автоматически).
        limit: Максимальное количество результатов (default: 20).

    Returns:
        Список словарей с полями: key, rank, bm25_score, snippet, source_type.
        Пустой список если BM25 недоступен, запрос пуст или произошла ошибка.
    """
    # Защита от пустого запроса
    normalized = _sanitize_query(query)
    if not normalized:
        return []

    results: List[BM25Result] = []
    start_time = time.perf_counter()

    try:
        with _get_fts5_connection() as conn:
            rows = conn.execute(
                """
                SELECT
                    path,
                    source,
                    snippet(memory_fts, ?, ?, ?, ?, ?) as snippet,
                    bm25(memory_fts) AS bm25_score
                FROM memory_fts
                WHERE memory_fts MATCH ?
                ORDER BY bm25_score, path      -- детерминированный порядок
                LIMIT ?
                """,
                (
                    SNIPPET_COLUMN,
                    SNIPPET_START_MARKER,
                    SNIPPET_END_MARKER,
                    SNIPPET_ELLIPSIS,
                    SNIPPET_MAX_TOKENS,
                    normalized,
                    limit
                )
            ).fetchall()

        for i, row in enumerate(rows, start=1):
            # Document-level ключ: используется единый make_join_key, чтобы
            # BM25 / FTS5 / semantic сходились на одинаковом значении для
            # одного и того же документа (см. KEY CONTRACT в ranking.py).
            # row['path'] — POSIX rel_path после reindex; make_join_key
            # сам нормализует, поэтому basename() не нужен (он бы
            # схлопнул archive/notes.md и current/notes.md в один ключ).
            results.append({
                "key": make_join_key(row['source'], row['path']),
                "rank": i,
                "bm25_score": row['bm25_score'],
                "snippet": row['snippet'],
                # Retrieval method identifier, not original document source
                "source_type": "bm25",
            })

        elapsed_ms = (time.perf_counter() - start_time) * 1000
        logging.info(
            "BM25 search completed: query=%r, results=%d, latency_ms=%.2f",
            normalized, len(results), elapsed_ms,
        )

    except (sqlite3.Error, OSError) as exc:
        logging.warning(
            "BM25 search failed (query=%r, limit=%d): %s",
            normalized, limit, exc
        )
        return []

    return results
