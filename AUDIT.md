# Code Audit — claude-4layer-memory

Статус находок по итогам code review. Обновляется по мере закрытия пунктов.

**Legend:** `[x]` resolved · `[ ]` open

## Resolved PRs

| PR | Finding | Squash commit |
| --- | --- | --- |
| #32 | FTS5 MATCH crash on raw user input | `c69efab` |
| #33 | cost_tracker KeyError on unknown model | `ced899d` |
| #34 | Per-chunk embedding during indexing | `e8ed1eb` |
| #35 | Windows UTF-8 guard in cost_tracker | `92961cb` |
| #36 | Naive timestamps in cost_tracker (UTC) | `0bdeb6d` |
| #37 | `@lru_cache` on instance methods (per-instance lazy cache) | `6800c4e` |

## High severity

- [x] **1. FTS5 MATCH crash on raw user query** — спецсимволы в сыром запросе, переданном напрямую в `MATCH`, роняли поиск. Исправлено санитайзингом (`sanitize_fts5_query()`) в `scripts/l4_fts5_search.py`. (PR #32) _Regression coverage: covered — прямые тесты на сам bug class (`sanitize_fts5_query()` + live FTS5 smoke) в `tests/test_l4_fts5_search.py`._
- [x] **2. cost_tracker KeyError on unknown model** — поиск цены бросал `KeyError` для моделей вне таблицы цен. Исправлено безопасной цепочкой фоллбэков в `_resolve_price()` и доступом через `.get()`. (PR #33)

## Medium severity

- [x] **3. Per-chunk embedding during indexing** — `index_directory` кодировал каждый чанк отдельным вызовом `model.encode([chunk])`. Исправлено батч-кодированием всех чанков файла через `_encode_documents()` (настраиваемый `L4_EMBED_BATCH_SIZE`). (PR #34)
- [x] **4. `@lru_cache` на методах экземпляра** — было: `_cached_search` / `_encode_query` декорированы `lru_cache` на методах, что удерживало экземпляры в памяти и делало кэш фактически глобальным. Исправлено: методы остаются на классе, а per-instance `lru_cache` создаётся лениво при первом вызове и хранится на экземпляре (`self._search_cache` / `self._encode_query_cache`) — кэш привязан к экземпляру, собирается GC вместе с ним и не шарится между экземплярами; работает и для объектов, созданных в обход `__init__`. (PR #37)
- [ ] **5. Широкий `except Exception`, глотающий ошибки** — несколько блоков `except Exception: # nosec` молча глотают ошибки, скрывая реальные сбои. Сузить исключения и/или логировать. _First slice: `_cached_search_impl` в `scripts/l4_fts5_search.py` сужен с `except Exception` до `except sqlite3.Error` (лог сохранён, неожиданные ошибки теперь пробрасываются) + regression-тесты на оба направления — PR-B. Остаётся открытым: semantic broad except (Chroma exception taxonomy + cross-collection graceful degradation), cost-tracking telemetry isolation, hybrid fan-out wrappers (`fetch_fts`/`fetch_semantic`/`fetch_bm25`), и `l4_semantic_global.py` — отдельными слайсами._
- [ ] **6. Несинхронизированные параллельные записи в SQLite** — одновременные записи в SQLite-базы могут привести к лок-контеншену/повреждению. Добавить сериализацию или WAL + retry.
- [x] **7. Naive timestamps в cost_tracker** — хранение переведено на timezone-aware UTC (`datetime.now(timezone.utc).isoformat()`); в `get_stats` колонка оборачивается в `datetime(timestamp)`, модификатор `'localtime'` убран — окно отсечения больше не зависит от часового пояса хоста. (PR #36)

## Low / hygiene

- [x] **8. Несогласованная обработка UTF-8 на Windows** — в `cost_tracker.py` не было гарда `hasattr(stream, "buffer")`, который есть в `l4_fts5_search.py` / `l4_semantic_global.py`. Унифицировано общим `configure_utf8_output()` (пропуск если уже UTF-8 → `reconfigure()` → фоллбэк на `codecs` только при наличии `buffer`), вызов из `main()`. (PR #35)
- [ ] **9. BOM в `package.json`** — ведущий byte-order mark; убрать.
- [ ] **10. Мёртвый код: `_rrf_stub`** — неиспользуемый placeholder; удалить или подключить.
- [ ] **11. Мусор в репо и пакетирование** — RAR-архив, одноразовые скрипты, process-доки `.md`, файл с пробелом в имени, а также двойное пакетирование и статичные badges. Почистить и консолидировать.

---

_Ведётся как handoff-документ для сессий ревью. Обновляйте статусы и ссылки на PR по мере закрытия находок._
