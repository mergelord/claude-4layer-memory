#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
L4 BM25 Search – независимый лексический источник для гибридного поиска.

Использует функцию bm25() встроенного FTS5-движка SQLite.
Возвращает результаты в контракте, ожидаемом RRF-слиянием.

Контракт возвращаемых результатов:
- key: document-level идентификатор "[source] filename"
- rank: позиция в выдаче BM25 (1-based, чем меньше тем лучше)
- bm25_score: сырое значение BM25 (отрицательное, чем ближе к 0 тем лучше)
- snippet: фрагмент текста с контекстом совпадения
- source_type: "bm25"
"""

import logging
from typing import Any, Dict, List

from l4_fts5_search import L4FTS5Search

# Параметры snippet() функции FTS5
SNIPPET_COLUMN = 2  # Индекс колонки content в FTS таблице
SNIPPET_START_MARKER = '»'
SNIPPET_END_MARKER = '«'
SNIPPET_ELLIPSIS = '...'
SNIPPET_MAX_TOKENS = 60  # Максимум токенов в snippet


def fetch_bm25_results(query: str, limit: int = 20) -> List[Dict[str, Any]]:
    """
    Возвращает список результатов BM25-поиска, готовых для подачи в RRF.

    Использует встроенную функцию bm25() в SQLite FTS5 для ранжирования.
    BM25 scores отрицательные — чем ближе к 0, тем релевантнее документ.

    Args:
        query: Поисковый запрос (FTS5 query syntax)
        limit: Максимальное количество результатов (default: 20)

    Returns:
        Список словарей с полями: key, rank, bm25_score, snippet, source_type.
        Пустой список если BM25 недоступен или произошла ошибка.

    Examples:
        >>> results = fetch_bm25_results("memory system")
        >>> results[0]["key"]
        '[global] architecture.md'
        >>> results[0]["source_type"]
        'bm25'
    """
    fts = L4FTS5Search()
    results = []

    try:
        with fts._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT
                    path,
                    source,
                    snippet(memory_fts, ?, ?, ?, ?, ?) as snippet,
                    bm25(memory_fts) AS bm25_score
                FROM memory_fts
                WHERE memory_fts MATCH ?
                ORDER BY bm25_score
                LIMIT ?
                """,
                (
                    SNIPPET_COLUMN,
                    SNIPPET_START_MARKER,
                    SNIPPET_END_MARKER,
                    SNIPPET_ELLIPSIS,
                    SNIPPET_MAX_TOKENS,
                    query,
                    limit
                )
            ).fetchall()

        for i, row in enumerate(rows, start=1):
            results.append({
                "key": f"[{row['source']}] {row['path']}",
                "rank": i,
                "bm25_score": row['bm25_score'],
                "snippet": row['snippet'],
                "source_type": "bm25",
            })

    except Exception as exc:
        logging.warning(
            "BM25 search failed (query=%r, limit=%d): %s",
            query, limit, exc
        )
        return []

    return results
