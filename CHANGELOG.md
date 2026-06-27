# Changelog

## Unreleased

### Documentation
- Added `docs/PRODUCTION_READINESS.md` with a concrete production release gate, readiness snapshot, and remaining risks.
- Added `docs/OPERATIONS.md` with install/upgrade, health, logging, reindex, budget, privacy, and incident runbooks.
- Rewrote `docs/INSTALL.md` to reflect the current Python 3.10+ / git-clone-only baseline and reproducible install path.
- Rewrote `docs/guides/CONFIGURATION.md` to document `L4_HOME`, logs, P3 guardrail env vars, routing privacy, and backup strategy.
- Updated `MCP_SERVER.md` to document the current MCP tool surface, safety defaults, and operational checks.

### CI
- Added non-blocking Ubuntu / Python 3.14 test coverage while keeping Python 3.10-3.13 blocking across Ubuntu, Windows, and macOS.

### Maintenance
- P4-1: `install.sh` and `install.bat` now install runtime dependencies with `constraints.txt` (`pip install -r requirements.txt -c constraints.txt`) so fresh installs use the documented reproducible baseline.

## [1.6.0] - 2026-06-23

### Breaking Changes
- **`graceful-shutdown-wrapper.py` переписан:** вместо захардкоженного списка 7
  личных хуков используется auto-discovery — сканирует `~/.claude/hooks/` для
  `stop-*.py` файлов. Пользователи с кастомным списком хуков в этом файле
  должны перейти на именование `stop-*.py` для своих хуков.

### Added
- **Hooks в репозитории:** `hooks/builtin/` (7 файлов) и `hooks/optional/` (1 файл)
  теперь версионируются в git. Без них 4-layer memory не работает.
  - `hooks/builtin/precompact-flush-l4.py` — сохраняет HOT/WARM перед компактом
  - `hooks/builtin/session-usage-logger.py` — логирует usage для ledger
  - `hooks/builtin/auto-remember.py` — ловит "запомни: X" → HOT memory
  - `hooks/builtin/load-context-on-start.py` — грузит MEMORY.md/decisions.md
  - `hooks/builtin/inject-verified-facts.py` — антигаллюцинация (CWD, user, date)
  - `hooks/builtin/hook_cache.py` — кэш для ChromaDB/sentence-transformers
  - `hooks/builtin/graceful-shutdown-wrapper.py` — обёртка для Stop hooks
  - `hooks/optional/crash-recovery.py` — восстановление после аварий
- `hooks/README.md` — документация по структуре hooks/ и auto-discovery

### Security
- **Token leak fix** (`dsm_telegram_monitor.py:583`): бот-токен в URL попадал
  в `str(HTTPError)` → утечка в логи. Добавлена `_sanitize_token()` для замены
  токена на `***` + regression test.

### Fixed
- `audit.py:191` — Python version gate обновлён с `>=3.7` на `>=3.10`
  (CI тестирует 3.10-3.13, код использует PEP 604).
- `README.md` — разделены installed runtime команды и repo-only dev инструменты
  (hybrid search, BM25, rerank, memory_lint).

### Maintenance
- `install.bat` / `install.sh` — копируют `hooks/builtin/*` при установке
- Deployed runtime синхронизирован: `~/.claude/hooks/` = repo (10/10 ключевых файлов)
- `~/.claude/VERSION` обновлён до 1.6.1 (был 1.4.0)
- Очистка deploy: удалены 16 orphaned bat-файлов, 8 backup-файлов, `cmd.exe`

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
  исправлены Windows-style backslash ключи (`archive\\notes.md`).

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
- проблема с access violation в pyarrow на Python 3.13 (обход через моки).
- несовместимость старых тестов с новым API (удалены).

### Tooling
- Создана утилита `paste_to_file.py` для безопасной вставки кода
  без артефактов копипасты.
- Создана утилита `apply_code.py` для консольной нормализации файлов.
