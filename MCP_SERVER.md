# MCP Server for Claude 4-Layer Memory

Model Context Protocol server for accessing the memory system from MCP-compatible clients.

---

## Capabilities

### Memory search tools

| Tool | Purpose | Mutates state |
| --- | --- | --- |
| `search_memory(query, limit=10, debug=False)` | FTS5 keyword search. | No |
| `hybrid_search_memory(query, limit=10, rerank=True, debug=False)` | Hybrid FTS5 + semantic + BM25 + RRF search with optional reranking. | No |
| `get_memory_stats()` | FTS5 index statistics. | No |
| `reindex_memory(confirm=False)` | Full FTS5 rebuild. Requires `confirm=True`. | Yes, only with confirmation |

### Cost tools

| Tool | Purpose | Mutates state |
| --- | --- | --- |
| `track_claude_usage(...)` | Record exact Claude token usage. | Yes |
| `get_cost_stats(days=7)` | Cost statistics. | No |
| `get_cost_stats_by_metadata(key="task", days=7)` | Cost stats grouped by metadata key. | No |
| `get_recent_cost_operations(limit=20)` | Recent cost ledger entries. | No |
| `get_cost_breakdown(days=7)` | Spending breakdown by model/category. | No |

### Code completion / routing tool

| Tool | Purpose | Guardrails |
| --- | --- | --- |
| `smart_complete(task, context="", max_tokens=4096)` | Anthropic-backed code task execution with routing learner feedback. | Input clamps, daily budget, cost tracking, routing privacy options. |

### Health tool

| Tool | Purpose | Mutates state |
| --- | --- | --- |
| `health_check(include_semantic=True)` | Readiness check for FTS5, semantic backend, routing learner, cost ledger, and host facts. | No |

### Resources

| Resource | Purpose |
| --- | --- |
| `memory://global/handoff` | HOT memory handoff. |
| `memory://global/decisions` | WARM memory decisions. |

---

## Safety defaults

### Destructive reindex is gated

`reindex_memory()` without confirmation is a no-op:

```json
{
  "success": false,
  "requires_confirmation": true
}
```

To rebuild deliberately:

```python
reindex_memory(confirm=True)
```

### Input clamps

MCP input guardrails cap pathological requests:

| Input | Limit |
| --- | --- |
| result limit | 1..100 |
| query text | 2,000 chars |
| smart-complete task | 100,000 chars |
| smart-complete context | 200,000 chars |
| max output tokens | 8,192 |

### Daily budget

`smart_complete` can be budget-capped:

```bash
export L4_DAILY_BUDGET_USD=5
```

When today's spend reaches the cap, `smart_complete` refuses before spending and returns `budget_exceeded: true`.

### Routing privacy

To avoid storing raw task text in routing history:

```bash
export ROUTING_STORE_TASK_TEXT=0
```

New routing outcomes store a `sha256:...` value instead of raw task text.

---

## Installation

Install dependencies from a full repository clone:

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt -c constraints.txt
```

Add the server to Claude Code settings.

Linux/macOS example:

```json
{
  "mcpServers": {
    "claude-4layer-memory": {
      "command": "python3",
      "args": ["/path/to/claude-4layer-memory/mcp_server.py"]
    }
  }
}
```

Windows example:

```json
{
  "mcpServers": {
    "claude-4layer-memory": {
      "command": "python",
      "args": ["C:\\path\\to\\claude-4layer-memory\\mcp_server.py"]
    }
  }
}
```

Restart Claude Code after updating settings.

---

## Environment variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `L4_HOME` | `~/.claude` | Relocates memory state, DBs, routing learner state, and logs. |
| `L4_MODEL` | `paraphrase-multilingual-MiniLM-L12-v2` | Sentence-transformers model. |
| `L4_PREWARM` | `1` | Enables semantic backend prewarm on server startup. Set `0`, `false`, or `no` to disable. |
| `L4_LOG_LEVEL` | implementation default | Structured logging verbosity. |
| `L4_DAILY_BUDGET_USD` | `0` / off | Daily budget for `smart_complete`. |
| `ROUTING_STORE_TASK_TEXT` | `1` | Set to `0`, `false`, or `no` to hash task text. |
| `ROUTING_HISTORY_MAX` | `0` / off | Optional routing-history retention limit for pruning. |
| `ANTHROPIC_API_KEY` | unset | Required only for real `smart_complete` calls. |
| `HF_TOKEN` | unset | Optional HuggingFace token for model downloads. |

---

## Testing

Run the server directly for debugging:

```bash
python mcp_server.py
```

Run via MCP dev tooling:

```bash
mcp dev mcp_server.py
```

Run repository smoke checks:

```bash
node cli/index.js selftest --no-semantic
node cli/index.js doctor --no-semantic
python -m pytest tests/test_mcp_e2e_smoke.py tests/test_p3_guardrails.py -v --tb=short
```

---

## Architecture

```text
MCP client
  -> mcp_server.py
    -> FTS5 search
    -> semantic search / ChromaDB
    -> BM25 / RRF / optional rerank
    -> cost tracker
    -> routing learner
    -> health check
```

The server keeps core objects at module scope so long-lived MCP processes can reuse FTS5, cost, routing, and semantic backend state instead of rebuilding them on every call.

---

## Operational docs

- `docs/OPERATIONS.md`
- `docs/PRODUCTION_READINESS.md`
- `docs/INSTALL.md`
- `docs/guides/CONFIGURATION.md`
