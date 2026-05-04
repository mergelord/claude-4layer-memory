#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MCP Server для Claude 4-Layer Memory System

Предоставляет доступ к памяти через Model Context Protocol:
- FTS5 keyword search
- Semantic search
- Memory statistics
- Cost tracking
"""

import sys
import logging
from typing import Any
from pathlib import Path

from mcp.server.fastmcp import FastMCP

# Настройка логирования в stderr (MCP requirement)
logging.basicConfig(
    level=logging.INFO,
    format='[%(levelname)s] %(message)s',
    stream=sys.stderr
)

# Импорт наших модулей
sys.path.insert(0, str(Path(__file__).parent))
from l4_fts5_search import L4FTS5Search  # noqa: E402
from cost_tracker import CostTracker  # noqa: E402

# Инициализация MCP сервера
mcp = FastMCP("claude-4layer-memory")

# Инициализация компонентов
fts5_search = L4FTS5Search()
cost_tracker = CostTracker()


@mcp.tool()
def search_memory(
    query: str,
    limit: int = 10,
    debug: bool = False,
) -> dict[str, Any]:
    """
    Поиск в памяти через FTS5 keyword search.

    Args:
        query: Поисковый запрос.
        limit: Максимум результатов (default: 10).
        debug: Если True, ответ содержит дополнительный блок ``meta`` со
            structured explanation (query tokens, candidate count,
            engine identification). Это first-class explainability — не
            текстовое логирование.

    Returns:
        ``{"success": True, "query": str, "count": int, "results": [...]}``.
        При ``debug=True`` добавляется ``"meta": {...}`` с полями
        ``engine``, ``query_tokens``, ``total_candidates``, ``limit``.
    """
    try:
        results = fts5_search.search(query, limit)

        response: dict[str, Any] = {
            "success": True,
            "query": query,
            "count": len(results),
            "results": [
                {
                    "path": r.path,
                    "snippet": r.snippet,
                    "rank": r.rank,
                    "source": r.source,
                }
                for r in results
            ],
        }

        if debug:
            response["meta"] = {
                "engine": "fts5",
                "query": query,
                "query_tokens": query.split(),
                "limit": limit,
                "total_candidates": len(results),
            }

        return response
    except Exception as e:
        logging.error("Search failed: %s", e)
        return {
            "success": False,
            "error": str(e),
        }


@mcp.tool()
def get_memory_stats() -> dict[str, Any]:
    """
    Получить статистику FTS5 индекса

    Returns:
        Статистика: количество документов, размер БД, источники
    """
    try:
        stats = fts5_search.stats()
        return {
            "success": True,
            "stats": stats
        }
    except Exception as e:
        logging.error("Stats failed: %s", e)
        return {
            "success": False,
            "error": str(e)
        }


@mcp.tool()
def get_cost_stats(days: int = 7) -> dict[str, Any]:
    """
    Получить статистику расходов на memory operations

    Args:
        days: Период в днях (default: 7)

    Returns:
        Статистика: операции, токены, стоимость
    """
    try:
        stats = cost_tracker.get_stats(days)
        return {
            "success": True,
            "stats": stats
        }
    except Exception as e:
        logging.error("Cost stats failed: %s", e)
        return {
            "success": False,
            "error": str(e)
        }


@mcp.tool()
def reindex_memory() -> dict[str, Any]:
    """
    Переиндексировать FTS5 базу данных

    Returns:
        Результат переиндексации
    """
    try:
        indexed_count = fts5_search.reindex_all()
        return {
            "success": True,
            "indexed_files": indexed_count,
        }
    except Exception as e:
        logging.error("Reindex failed: %s", e)
        return {
            "success": False,
            "error": str(e)
        }


# Resource для чтения памяти напрямую
@mcp.resource("memory://global/handoff")
def get_global_handoff() -> str:
    """Читает HOT memory (handoff.md) из глобальной памяти"""
    try:
        handoff_path = Path.home() / ".claude" / "memory" / "handoff.md"
        if handoff_path.exists():
            return handoff_path.read_text(encoding='utf-8')
        return "# No handoff data"
    except Exception as e:
        logging.error("Failed to read handoff: %s", e)
        return f"# Error: {e}"


@mcp.resource("memory://global/decisions")
def get_global_decisions() -> str:
    """Читает WARM memory (decisions.md) из глобальной памяти"""
    try:
        decisions_path = Path.home() / ".claude" / "memory" / "decisions.md"
        if decisions_path.exists():
            return decisions_path.read_text(encoding='utf-8')
        return "# No decisions data"
    except Exception as e:
        logging.error("Failed to read decisions: %s", e)
        return f"# Error: {e}"


if __name__ == "__main__":
    # Запуск MCP сервера
    mcp.run()
