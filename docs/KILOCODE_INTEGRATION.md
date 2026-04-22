# KiloCode Integration

**Дата:** 2026-04-22  
**Источник:** https://github.com/Kilo-Org/kilocode

---

## Обзор

Интеграция улучшений из KiloCode в Claude 4-Layer Memory System:

1. ✅ **Cost Tracking** - отслеживание расхода токенов
2. ✅ **MCP Server** - доступ к памяти через Model Context Protocol
3. ✅ **Memory Lint** - двухслойная валидация (уже было)
4. ✅ **Pre-commit Hook** - автоматическая валидация перед коммитом

---

## 1. Cost Tracking

**Файл:** `scripts/cost_tracker.py`

### Возможности

- Отслеживание операций с памятью (read/write/search)
- Подсчёт токенов (input/output)
- Вычисление стоимости по моделям (Opus/Sonnet/Haiku)
- SQLite база данных для истории
- Статистика за период

### Использование

```bash
# Статистика за 7 дней
python scripts/cost_tracker.py stats --days 7

# Записать операцию
python scripts/cost_tracker.py track \
  --operation "semantic_search" \
  --input-tokens 1500 \
  --output-tokens 500 \
  --model "claude-sonnet-4"
```

### Интеграция

Cost tracker автоматически используется в:
- `l4_fts5_search.py` - FTS5 keyword search
- `semantic_search.py` - semantic search
- `mcp_server.py` - MCP Server operations

---

## 2. MCP Server

**Файл:** `mcp_server.py`

### Возможности

- **Tools:**
  - `search_memory(query, limit)` - FTS5 keyword search
  - `get_memory_stats()` - статистика индекса
  - `get_cost_stats(days)` - статистика расходов
  - `reindex_memory()` - переиндексация

- **Resources:**
  - `memory://global/handoff` - HOT memory (handoff.md)
  - `memory://global/decisions` - WARM memory (decisions.md)

### Использование

```bash
# Запуск MCP сервера
python mcp_server.py
```

### Конфигурация Claude Desktop

Добавить в `~/.claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "claude-4layer-memory": {
      "command": "python",
      "args": ["C:/BAT/claude-4layer-memory/mcp_server.py"]
    }
  }
}
```

---

## 3. Memory Lint (Enhanced)

**Файл:** `scripts/memory_lint.py`

### Двухслойная валидация

**Layer 1: Deterministic Checks**
- Ghost links (ссылки на несуществующие файлы)
- Orphan files (файлы без ссылок)
- Duplicates (дубликаты контента)
- File sizes (большие файлы)
- Memory age (устаревшие записи)

**Layer 2: LLM-based Checks** (опционально)
- Contradictions (противоречия)
- Outdated claims (устаревшие утверждения)
- Consistency (согласованность)
- Completeness (полнота)

### Использование

```bash
# Quick mode (только Layer 1)
python scripts/memory_lint.py --quick

# Full validation (Layer 1 + Layer 2)
python scripts/memory_lint.py

# Только Layer 1
python scripts/memory_lint.py --layer 1

# Сохранить отчёт
python scripts/memory_lint.py --report report.json
```

---

## 4. Pre-commit Hook

**Файл:** `.git/hooks/pre-commit`

### Возможности

- Автоматический запуск Memory Lint перед каждым коммитом
- Quick mode (быстрая проверка)
- Блокировка коммита при критических ошибках
- Возможность пропустить проверку (`--no-verify`)

### Установка

Hook уже установлен в `.git/hooks/pre-commit` и активен.

### Использование

```bash
# Обычный коммит (с проверкой)
git commit -m "message"

# Пропустить проверку
git commit --no-verify -m "message"
```

### Поведение

- ✅ Если Memory Lint проходит → коммит разрешён
- ❌ Если Memory Lint находит ошибки → коммит блокируется
- ⚠️ Если Python не найден → проверка пропускается (warning)

---

## Конфликты с текущей реализацией

### ✅ Нет конфликтов

Все компоненты интегрированы без конфликтов:

1. **Cost Tracker** - новый компонент, не пересекается с существующими
2. **MCP Server** - новый компонент, использует существующие модули
3. **Memory Lint** - уже был реализован, улучшений не требуется
4. **Pre-commit Hook** - новый компонент, не влияет на существующие hooks

### Совместимость с SessionStart/Stop hooks

Pre-commit hook работает независимо от SessionStart/Stop hooks:
- SessionStart hooks - загрузка контекста при старте сессии
- Stop hooks - сохранение контекста при завершении сессии
- Pre-commit hook - валидация перед git commit

Все три системы работают параллельно без конфликтов.

---

## Roadmap

### Реализовано ✅

- [x] Cost Tracking для memory operations
- [x] MCP Server для доступа к памяти
- [x] Memory Lint с двухслойной валидацией
- [x] Pre-commit hook для автоматической валидации

### Будущие улучшения 💡

- [ ] Dashboard для визуализации cost statistics
- [ ] Автоматическая ротация памяти на основе cost tracking
- [ ] MCP Server: поддержка semantic search
- [ ] Memory Lint: автоматическое исправление простых ошибок
- [ ] Pre-commit hook: интеграция с CI/CD

---

## Благодарности

Спасибо проекту [KiloCode](https://github.com/Kilo-Org/kilocode) за идеи и вдохновение!
