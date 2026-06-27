# Configuration Guide

Configuration reference for Claude 4-Layer Memory System.

---

## Configuration model

The system is file-based by default and uses environment variables for deployment/runtime overrides.

Primary files and directories:

| Path | Purpose |
| --- | --- |
| `~/.claude/GLOBAL_PROJECTS.md` | Project registry. |
| `~/.claude/memory/` | Global memory. |
| `~/.claude/projects/<encoded-project>/memory/` | Project memory. |
| `~/.claude/memory_fts5.db` | FTS5 index. Regenerable. |
| `~/.claude/semantic_db_global/` | ChromaDB semantic index. Regenerable. |
| `~/.claude/memory_costs.db` | Cost ledger. |
| `~/.claude/routing_learner_db/` | Routing learner state. |
| `~/.claude/logs/` | Structured logs. |

Set `L4_HOME` to relocate the whole layout.

---

## `L4_HOME`

`L4_HOME` is the root for memory state, DBs, routing data, and logs.

Default:

```text
~/.claude
```

Example:

```bash
export L4_HOME=/srv/claude-memory
```

Derived paths:

| Derived path | Default |
| --- | --- |
| memory dir | `~/.claude/memory` |
| projects dir | `~/.claude/projects` |
| FTS5 DB | `~/.claude/memory_fts5.db` |
| semantic DB | `~/.claude/semantic_db_global` |
| costs DB | `~/.claude/memory_costs.db` |
| routing DB | `~/.claude/routing_learner_db` |
| logs | `~/.claude/logs` |

Changing `L4_HOME` does not migrate data. It points the runtime at a different state root.

---

## Project registry: `GLOBAL_PROJECTS.md`

Location:

```text
<L4_HOME>/GLOBAL_PROJECTS.md
```

Default:

```text
~/.claude/GLOBAL_PROJECTS.md
```

Recommended entry format:

```markdown
### Project Name
**Path:** `/absolute/path/to/project`
**Memory:** `~/.claude/projects/encoded-project-path/memory/`
**Status:** ✅ Active

**Description:**
Short project description.
```

Use absolute paths. Keep inactive projects marked or remove them when no longer needed.

---

## Memory path encoding

Common encoding rules:

1. Replace `/` with `-`
2. Replace `:` with `--`
3. Replace spaces with `-`
4. Remove leading `/`

Examples:

| Project path | Encoded project memory path |
| --- | --- |
| `/home/user/projects/app` | `home-user-projects-app` |
| `C:\Projects\MyApp` | `C--Projects-MyApp` |
| `/Users/name/my project` | `Users-name-my-project` |

---

## Environment variables

### Core paths and model

| Variable | Default | Description |
| --- | --- | --- |
| `L4_HOME` | `~/.claude` | Root for memory state, DBs, routing, and logs. |
| `L4_MODEL` | `paraphrase-multilingual-MiniLM-L12-v2` | Sentence-transformers embedding model. |
| `HF_TOKEN` | unset | Optional HuggingFace token for model downloads/rate limits. |

Example:

```bash
export L4_MODEL=sentence-transformers/all-MiniLM-L6-v2
```

### MCP/runtime behavior

| Variable | Default | Description |
| --- | --- | --- |
| `L4_PREWARM` | `1` | Enables background semantic backend prewarm when `mcp_server.py` starts. Use `0`, `false`, or `no` to disable. |
| `L4_LOG_LEVEL` | implementation default | Log level for structured logging. |
| `ANTHROPIC_API_KEY` | unset | Required only for Anthropic-backed `smart_complete`. |
| `PYTHON_BIN` | platform default | Python executable used by Node CLI commands. |

### Cost guardrails

| Variable | Default | Description |
| --- | --- | --- |
| `L4_DAILY_BUDGET_USD` | `0` / off | Optional daily USD budget for `smart_complete`. When today's spend reaches the cap, calls are blocked before spending. |

Examples:

```bash
export L4_DAILY_BUDGET_USD=5
export L4_DAILY_BUDGET_USD=0  # disable
```

### Routing privacy and retention

| Variable | Default | Description |
| --- | --- | --- |
| `ROUTING_STORE_TASK_TEXT` | `1` | Set `0`, `false`, or `no` to store a `sha256:...` hash instead of raw task text in routing history. |
| `ROUTING_HISTORY_MAX` | `0` / off | Max routing-history entries used by manual pruning. |

Examples:

```bash
export ROUTING_STORE_TASK_TEXT=0
export ROUTING_HISTORY_MAX=1000
```

Pruning is not automatic by default. The limit is consumed by the routing learner pruning path.

---

## Search/index configuration

### FTS5 index

Default DB:

```text
<L4_HOME>/memory_fts5.db
```

Normal maintenance:

```bash
python scripts/l4_fts5_search.py reindex --incremental
```

Full rebuild:

```bash
python scripts/l4_fts5_search.py reindex
```

MCP full rebuild requires explicit confirmation:

```python
reindex_memory(confirm=True)
```

### Semantic index

Default DB directory:

```text
<L4_HOME>/semantic_db_global
```

Build/rebuild:

```bash
python scripts/l4_semantic_global.py index-all
```

---

## Logging

Logs live under:

```text
<L4_HOME>/logs/
```

Use logs for:

- semantic prewarm failures
- hybrid timing/debug investigation
- `smart_complete` budget blocks
- routing learner bookkeeping failures
- health-check degradation

---

## Backup strategy

Back up user-authored memory/config:

- `GLOBAL_PROJECTS.md`
- `memory/`
- `projects/*/memory/`
- any custom config files you created

Usually exclude regenerable indexes:

- `semantic_db*`
- `memory_fts5.db`
- `*.sqlite3`

Example:

```bash
tar -czf claude-memory-backup.tar.gz \
  --exclude='semantic_db*' \
  --exclude='*.sqlite3' \
  --exclude='memory_fts5.db' \
  ~/.claude/GLOBAL_PROJECTS.md \
  ~/.claude/memory \
  ~/.claude/projects/*/memory
```

---

## Best practices

- Keep `GLOBAL_PROJECTS.md` current.
- Prefer incremental reindex for routine maintenance.
- Treat full reindex as deliberate maintenance.
- Use `L4_DAILY_BUDGET_USD` before enabling frequent `smart_complete` use.
- Use `ROUTING_STORE_TASK_TEXT=0` for privacy-sensitive environments.
- Run `cm selftest` or `node cli/index.js selftest` after upgrades.
- Read `CHANGELOG.md` for release-specific reindex requirements.
