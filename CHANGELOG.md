# Changelog

## [1.5.1] - 2026-05-29

### Documentation
- README обновлён: актуализированы факты и добавлен раздел
  «Reliability & Hardening», отражающий фиксы 1.5.0 (commit c6353d9).

### Maintenance
- **AUDIT #11 (repo hygiene):** из репозитория удалены one-off скрипты
  (`apply_*.py`, `clean_artifacts.py`, `paste_to_file.py`, `write_docs.py`,
  `analyze_project.py`), PyInstaller-спека `PasteToFile.spec`, RAR-архив и
  файл со сломанным именем, `temp_code.txt`, а также transient-отчёты
  (`ANTIPATTERNS_FIX.md`, `ARCHITECTURE_ANALYSIS.md`, `CODE_QUALITY_REPORT.md`,
  `FINAL_SUMMARY.md`, `PROJECT_STATUS.md`); тест приватности перенесён в
  `tests/` (PR #40).
- Версия проекта поднята до 1.5.1 (`VERSION`, `package.json`).

### Note
- Только документация и гигиена репозитория — изменений в рантайм-коде нет.
  Шаги апгрейда из 1.5.0 (reindex FTS5 + пересборка ChromaDB) остаются
  актуальны только при переходе с версий ниже 1.5.0.

## [1.5.0] - 2026-05-29

### Fixed
- **AUDIT #1:** runtime fix с регрессионным покрытием.
- **AUDIT #5 (first slice):** broad `except` в `_cached_search_impl` (FTS5)
  сужен до `sqlite3.Error` — ожидаемые SQLite-ошибки по-прежнему
  мягко деградируют в `tuple()` (с логированием), а неожиданные
  пробрасываются. Добавлены регрессионные тесты (PR #39).
  Остальные broad-except (semantic / cost / hybrid wrappers,
  `l4_semantic_global.py`) отложены — AUDIT #5 остаётся открытым.
- См. запись 2026-05-27 (N-4, RRF basename collision) — вошла в этот релиз.

### Maintenance
- Убран UTF-8 BOM из `package.json` (AUDIT #9).
- Версия проекта поднята до 1.5.0 (`VERSION`, `package.json`).

### Operational requirement after upgrade
- **`l4_search.bat reindex`** (или `python scripts/l4_fts5_search.py reindex`) и
  **пересборка ChromaDB коллекций** (`python scripts/l4_semantic_global.py index-all`)
  — нужны, чтобы N-4 RRF-фикс применился к уже-проиндексированным данным.

## 2026-05-27

### Fixed
- **Bug N-4 (RRF basename collision, silent correctness):** join-key для
  Reciprocal Rank Fusion во всех трёх движках (FTS5, BM25, semantic) теперь
  строится из **POSIX относительного document path** вместо
  `os.path.basename(path)`. Раньше `archive/notes.md` и `current/notes.md`
  в одном source тихо сливались в один `[source] notes.md` ключ, и RRF
  возвращал смешанные результаты разных файлов под одним идентификатором.
- Добавлена централизованная функция `ranking.normalize_document_path()`,
  и `ranking.make_join_key()` теперь сам её вызывает — callers больше не
  могут забыть нормализацию.
- `_index_single_file` в FTS5 перешел с `str(path)` на `.as_posix()` —
  исправлены Windows-style backslash ключи (`archive\notes.md`).

### Operational requirement after upgrade
- **`l4_search.bat reindex`** (или `python scripts/l4_fts5_search.py reindex`) —
  старые FTS5 БД содержат basename / backslash в колонке `path`.
- **Пересоздать ChromaDB коллекции** (`python scripts/l4_semantic_global.py index-all`) —
  `metadata["file"]` теперь POSIX rel_path, старые коллекции продолжат
  работать с basename до пересборки.
- Без этих шагов баг сохранится для уже-проиндексированных данных.

## 2026-05-07

### Added
- **Cross-Encoder Reranking:** финальный этап гибридного поиска с использованием
  `cross-encoder/ms-marco-MiniLM-L-6-v2` для переупорядочивания топ-20 результатов
  после RRF слияния. Повышает точность релевантности верхних результатов.
- Отображение `rerank_score` в выводе команды `hybrid` для прозрачности работы reranking.

## 2026-05-05

### Added
- **URC-1 (Unified Ranking Contract):** гибридная архитектура поиска
  с RRF-ready хуком, кэшированием эмбеддингов, безопасным получением
  коллекций и метриками времени поиска (PR #25).
- **P1 (Embedding Gateway):** единый шлюз для получения эмбеддингов
  поисковых запросов через `_encode_query()`, запрет прямых вызовов
  `model.encode()` (PR #26).

### Changed
- `l4_semantic_global.py` — полный рефакторинг с фокусом на
  hybrid-ready архитектуру и безопасность коллекций.
- Тесты для `l4_semantic_global` заменены на версию v2 с моками,
  старый файл удалён.

### Fixed
- роблема с access violation в pyarrow на Python 3.13 (обход через моки).
- есовместимость старых тестов с новым API (удалены).

### Tooling
- Создана утилита `paste_to_file.py` для безопасной вставки кода
  без артефактов копипасты.
- Создана утилита `apply_code.py` для консольной нормализации файлов.
