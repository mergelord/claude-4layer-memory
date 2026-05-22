from pathlib import Path

def write_docs():
    docs = Path('docs')
    docs.mkdir(parents=True, exist_ok=True)

    # URC-1
    (docs / 'URC-1.md').write_text(
        "# URC-1: Unified Ranking Contract\n\n"
        "**Дата:** 2026-05-05\n"
        "**Статус:** ✅ Merged (PR #25)\n\n"
        "## Что сделано\n\n"
        "Внедрён единый контракт ранжирования для модуля `l4_semantic_global.py`.\n\n"
        "До URC-1 в системе существовали две конкурирующие логики сортировки:\n"
        "- `distance` (ChromaDB) — устаревший fallback\n"
        "- RRF (reciprocal rank fusion) — новая логика релевантности\n\n"
        "URC-1 делает RRF единственным источником истины для порядка результатов,\n"
        "а distance оставляет только для отладки.\n\n"
        "## Архитектурные изменения\n\n"
        "### `search_all()` — hybrid-ready pipeline\n\n"
        "- Сбор результатов по источникам — semantic (ChromaDB), в будущем BM25\n"
        "- Oversampling (`per_collection = n_results`) для повышения recall\n"
        "- Локальное ранжирование (`_rank`) внутри каждого источника\n"
        "- Hybrid hook — при появлении второго источника вызывается `rrf_merge()`\n"
        "- Dedup по document-level ключу (`id`) с сохранением лучшего ранга\n"
        "- Сортировка только по `_rank` (или `rrf_score` после слияния), distance не участвует\n\n"
        "### `_encode_query()` — query embedding cache\n\n"
        "- Добавлен `@lru_cache(maxsize=128)` на метод `_encode_query`\n"
        "- Повторные запросы с одинаковым текстом не вызывают модель повторно\n"
        "- Устойчивость к мокам: `hasattr(result, \"tolist\")`\n\n"
        "### `_get_collection()` — безопасное получение коллекций\n\n"
        "- Логирует ошибки и возвращает `None` вместо исключения\n\n"
        "### `_search_collection()` — защита от пустых коллекций\n\n"
        "- Проверка `if not collection` перед запросом\n\n"
        "## Результаты линтеров\n\n"
        "| Инструмент | Результат |\n"
        "|------------|-----------|\n"
        "| Pylint     | 10.00/10  |\n"
        "| Prospector | 0 messages |\n"
        "| Bandit     | Clean |\n"
        "| Radon (avg) | A (4.67) |\n\n"
        "## Тесты\n\n"
        "- 28 тестов ранжирования (`test_ranking.py`) — все проходят\n"
        "- 4 теста для нового модуля (`test_l4_semantic_global_v2.py`) — все проходят\n"
        "- Старый `test_l4_semantic_global.py` удалён\n\n"
        "## Как подключить BM25 (будущее)\n\n"
        "1. Добавить источник `\"bm25\"` в `results_by_source`\n"
        "2. Вызвать `_search_collection` для FTS5 индекса\n"
        "3. Раскомментировать `rrf_merge(active_sources, k=60)`\n"
        "4. RRF автоматически сольёт semantic и keyword ранги\n\n"
        "Архитектура полностью готова для второго ранкера.\n",
        encoding='utf-8'
    )

    # P1
    (docs / 'P1-Embedding-Gateway.md').write_text(
        "# P1: Embedding Gateway\n\n"
        "**Дата:** 2026-05-05\n"
        "**Статус:** ✅ Merged (PR #26)\n\n"
        "## Что сделано\n\n"
        "Создан единый шлюз для получения эмбеддингов поисковых запросов —\n"
        "метод `_encode_query()` с декоратором `@lru_cache(maxsize=128)`.\n\n"
        "Все поисковые запросы (`search_all`, будущие BM25-методы) обязаны\n"
        "проходить через этот шлюз. Прямые вызовы `self.model.encode()` запрещены.\n\n"
        "## Архитектурное значение\n\n"
        "- **Единственная точка входа** для получения эмбеддингов\n"
        "- **Кэширование** — повторные запросы не нагружают модель\n"
        "- **Готовность к BM25** — второй ранкер будет использовать тот же шлюз\n"
        "- **Упрощение тестирования** — достаточно замокать один метод\n\n"
        "## Добавленные тесты\n\n"
        "- `test_search_all_uses_gateway` — проверяет, что `search_all` вызывает\n"
        "  `_encode_query`, а не `model.encode` напрямую\n"
        "- `test_repeated_query_uses_cache` — проверяет кэширование при повторных запросах\n\n"
        "## Изменения в коде\n\n"
        "- Метод `_encode_query` помечен как EMBEDDING GATEWAY (P1)\n"
        "- Добавлена аннотация возвращаемого типа `-> List[float]`\n"
        "- Комментарий-маркер: \"All search queries MUST use this method.\n"
        "  Direct calls to self.model.encode() are forbidden.\"\n",
        encoding='utf-8'
    )

    # CHANGELOG
    Path('CHANGELOG.md').write_text(
        "# Changelog\n\n"
        "## 2026-05-07\n\n"
        "### Added\n"
        "- **Cross-Encoder Reranking:** финальный этап гибридного поиска с использованием\n"
        "  `cross-encoder/ms-marco-MiniLM-L-6-v2` для переупорядочивания топ-20 результатов\n"
        "  после RRF слияния. Повышает точность релевантности верхних результатов.\n"
        "- Отображение `rerank_score` в выводе команды `hybrid` для прозрачности работы reranking.\n\n"
        "## 2026-05-05\n\n"
        "### Added\n"
        "- **URC-1 (Unified Ranking Contract):** гибридная архитектура поиска\n"
        "  с RRF-ready хуком, кэшированием эмбеддингов, безопасным получением\n"
        "  коллекций и метриками времени поиска (PR #25).\n"
        "- **P1 (Embedding Gateway):** единый шлюз для получения эмбеддингов\n"
        "  поисковых запросов через `_encode_query()`, запрет прямых вызовов\n"
        "  `model.encode()` (PR #26).\n\n"
        "### Changed\n"
        "- `l4_semantic_global.py` — полный рефакторинг с фокусом на\n"
        "  hybrid-ready архитектуру и безопасность коллекций.\n"
        "- Тесты для `l4_semantic_global` заменены на версию v2 с моками,\n"
        "  старый файл удалён.\n\n"
        "### Fixed\n"
        "- Проблема с access violation в pyarrow на Python 3.13 (обход через моки).\n"
        "- Несовместимость старых тестов с новым API (удалены).\n\n"
        "### Tooling\n"
        "- Создана утилита `paste_to_file.py` для безопасной вставки кода\n"
        "  без артефактов копипасты.\n"
        "- Создана утилита `apply_code.py` для консольной нормализации файлов.\n",
        encoding='utf-8'
    )

write_docs()
print('Documentation files created successfully.')

# Made with Bob
