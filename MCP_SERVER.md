# MCP Server для Claude 4-Layer Memory

Model Context Protocol сервер для доступа к системе памяти из любых MCP-совместимых клиентов.

## Возможности

### Tools (функции)
- `search_memory(query, limit)` - FTS5 keyword поиск
- `get_memory_stats()` - статистика FTS5 индекса
- `get_cost_stats(days)` - статистика расходов на операции
- `reindex_memory()` - переиндексация памяти

### Resources (данные)
- `memory://global/handoff` - HOT memory (последние события)
- `memory://global/decisions` - WARM memory (важные решения)

## Установка

### 1. Установить зависимости

```bash
pip install -r requirements.txt
```

### 2. Настроить Claude Code

Добавить в `~/.claude/settings.json`:

```json
{
  "mcpServers": {
    "claude-4layer-memory": {
      "command": "python",
      "args": [
        "/path/to/claude-4layer-memory/mcp_server.py"
      ]
    }
  }
}
```

**Windows:**
```json
{
  "mcpServers": {
    "claude-4layer-memory": {
      "command": "python",
      "args": [
        "C:\\BAT\\claude-4layer-memory\\mcp_server.py"
      ]
    }
  }
}
```

### 3. Перезапустить Claude Code

После добавления конфигурации перезапустите Claude Code для подключения MCP сервера.

## Использование

### В Claude Code

После подключения MCP сервера, Claude автоматически получит доступ к tools:

```
User: Найди в памяти информацию о FTS5 search

Claude: [использует search_memory("FTS5 search")]
```

### Из других MCP клиентов

Любой MCP-совместимый клиент может подключиться к серверу:

```python
from mcp import ClientSession

async with ClientSession("python", ["mcp_server.py"]) as session:
    result = await session.call_tool("search_memory", {
        "query": "memory system",
        "limit": 5
    })
    print(result)
```

## Тестирование

```bash
# Запуск сервера напрямую (для отладки)
python mcp_server.py

# Проверка tools через MCP CLI
mcp dev mcp_server.py
```

## Архитектура

```
┌─────────────────┐
│  MCP Client     │  (Claude Code, ChatGPT, VS Code, etc.)
│  (любой)        │
└────────┬────────┘
         │ MCP Protocol
         │
┌────────▼────────┐
│  mcp_server.py  │
│                 │
│  Tools:         │
│  - search       │
│  - stats        │
│  - reindex      │
│                 │
│  Resources:     │
│  - handoff      │
│  - decisions    │
└────────┬────────┘
         │
    ┌────▼─────┬──────────┬──────────┐
    │          │          │          │
┌───▼───┐ ┌───▼───┐ ┌───▼───┐ ┌───▼───┐
│ FTS5  │ │Semantic│ │ Cost  │ │Memory │
│Search │ │ Search │ │Tracker│ │ Lint  │
└───────┘ └────────┘ └───────┘ └───────┘
```

## Преимущества MCP

1. **Универсальность** - работает с любым MCP клиентом
2. **Стандартизация** - единый протокол для всех AI приложений
3. **Расширяемость** - легко добавлять новые tools и resources
4. **Безопасность** - контроль доступа через MCP permissions

## Вдохновлено

- [Model Context Protocol](https://modelcontextprotocol.io/)
- [KiloCode MCP Server Marketplace](https://github.com/Kilo-Org/kilocode)

## Лицензия

MIT
