# URC-1: Unified Ranking Contract

**ата:** 2026-05-05
**Статус:** ✅ Merged (PR #25)

## то сделано

недрён единый контракт ранжирования для модуля `l4_semantic_global.py`.

о URC-1 в системе существовали две конкурирующие логики сортировки:
- `distance` (ChromaDB) — устаревший fallback
- RRF (reciprocal rank fusion) — новая логика релевантности

URC-1 делает RRF единственным источником истины для порядка результатов,
а distance оставляет только для отладки.

## рхитектурные изменения

### `search_all()` — hybrid-ready pipeline

- Сбор результатов по источникам — semantic (ChromaDB), в будущем BM25
- Oversampling (`per_collection = n_results`) для повышения recall
- окальное ранжирование (`_rank`) внутри каждого источника
- Hybrid hook — при появлении второго источника вызывается `rrf_merge()`
- Dedup по document-level ключу (`id`) с сохранением лучшего ранга
- Сортировка только по `_rank` (или `rrf_score` после слияния), distance не участвует

### `_encode_query()` — query embedding cache

- обавлен `@lru_cache(maxsize=128)` на метод `_encode_query`
- овторные запросы с одинаковым текстом не вызывают модель повторно
- стойчивость к мокам: `hasattr(result, 'tolist')`

### `_get_collection()` — безопасное получение коллекций

- огирует ошибки и возвращает `None` вместо исключения

### `_search_collection()` — защита от пустых коллекций

- роверка `if not collection` перед запросом

## езультаты линтеров

| нструмент | езультат |
|------------|-----------|
| Pylint     | 10.00/10  |
| Prospector | 0 messages |
| Bandit     | Clean |
| Radon (avg) | A (4.67) |

## Тесты

- 28 тестов ранжирования (`test_ranking.py`) — все проходят
- 4 теста для нового модуля (`test_l4_semantic_global_v2.py`) — все проходят
- Старый `test_l4_semantic_global.py` удалён

## ак подключить BM25 (будущее)

1. обавить источник `"bm25"` в `results_by_source`
2. ызвать `_search_collection` для FTS5 индекса
3. аскомментировать `rrf_merge(active_sources, k=60)`
4. RRF автоматически сольёт semantic и keyword ранги

рхитектура полностью готова для второго ранкера.
