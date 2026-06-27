# Operations Runbook

Operational runbook for running and maintaining Claude 4-Layer Memory in a production-like local setup.

---

## Quick health commands

From a full repository clone:

```bash
node cli/index.js doctor
node cli/index.js selftest
```

Fast mode without semantic/Chroma probe:

```bash
node cli/index.js doctor --no-semantic
node cli/index.js selftest --no-semantic
```

Direct Python health check:

```bash
python scripts/health_check.py --json
python scripts/health_check.py --json --no-semantic
```

---

## Release gate

Before tagging a release, run the release gate from a full clone.

Fast gate:

```bash
node cli/index.js release-gate --quick --no-semantic
```

Full gate:

```bash
node cli/index.js release-gate --no-semantic
```

Drop `--no-semantic` when semantic dependencies and local model cache are available.

---

## Install / upgrade flow

### Fresh install

```bash
git clone https://github.com/mergelord/claude-4layer-memory.git
cd claude-4layer-memory

python -m pip install --upgrade pip
python -m pip install -r requirements.txt -c constraints.txt
python -m pip install -r requirements-dev.txt

# Windows
.\audit.bat
.\install.bat

# Linux/macOS
./audit.sh
./install.sh
```

### Upgrade existing clone

```bash
git pull --ff-only
python -m pip install --upgrade pip
python -m pip install -r requirements.txt -c constraints.txt
python -m pip install -r requirements-dev.txt
node cli/index.js selftest --no-semantic
```

If search quality or indexed paths changed in the release notes, rebuild indexes explicitly:

```bash
python scripts/l4_fts5_search.py reindex
python scripts/l4_semantic_global.py index-all
```

For MCP full FTS5 rebuild, remember that `reindex_memory` requires explicit confirmation.

---

## Environment variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `L4_HOME` | `~/.claude` | Relocates memory state, DBs, routing learner data, and logs. |
| `L4_MODEL` | `paraphrase-multilingual-MiniLM-L12-v2` | Sentence-transformers embedding model. |
| `L4_PREWARM` | `1` | Enables background semantic backend prewarm at MCP server startup. Set `0`, `false`, or `no` to disable. |
| `L4_LOG_LEVEL` | implementation default | Controls structured JSON log verbosity. |
| `L4_DAILY_BUDGET_USD` | `0` / off | Optional daily spend cap for `smart_complete`. |
| `ROUTING_STORE_TASK_TEXT` | `1` | Set `0`, `false`, or `no` to store a SHA-256 task hash instead of raw task text. |
| `ROUTING_HISTORY_MAX` | `0` / off | Optional max routing-history entries for manual pruning. |
| `HF_TOKEN` | unset | Optional HuggingFace token for model downloads/rate limits. |
| `ANTHROPIC_API_KEY` | unset | Required only for Anthropic-backed `smart_complete` calls. |
| `PYTHON_BIN` | `python` on Windows, `python3` elsewhere | Overrides Python executable used by Node CLI commands such as `selftest`. |

---

## Logs

Structured JSON logs are written under:

```text
<L4_HOME>/logs/
```

Default when `L4_HOME` is unset:

```text
~/.claude/logs/
```

Use logs to investigate:

- semantic prewarm failures
- hybrid timing regressions
- smart-complete budget blocks
- routing learner bookkeeping warnings
- health-check degradation

---

## Reindex policy

### Safe read-only checks

```bash
node cli/index.js doctor --no-semantic
python scripts/l4_fts5_search.py stats
```

### Incremental reindex

Use incremental reindex for normal maintenance when available from the CLI path:

```bash
python scripts/l4_fts5_search.py reindex --incremental
```

### Full reindex

Full reindex is destructive for the FTS5 index and should be deliberate:

```bash
python scripts/l4_fts5_search.py reindex
```

MCP full reindex is guarded and requires:

```python
reindex_memory(confirm=True)
```

Without `confirm=True`, it must return `requires_confirmation: true` and perform no rebuild.

---

## Budget guardrail

To cap Anthropic-backed `smart_complete` usage:

```bash
export L4_DAILY_BUDGET_USD=5
```

When today's spend reaches the cap, `smart_complete` returns:

```json
{
  "success": false,
  "budget_exceeded": true
}
```

Unset the variable or set it to `0` to disable the guard.

---

## Privacy guardrail

To avoid storing raw task text in routing history:

```bash
export ROUTING_STORE_TASK_TEXT=0
```

New routing outcomes then store a `sha256:...` value instead of raw task text.

To cap retained routing outcomes:

```bash
export ROUTING_HISTORY_MAX=1000
```

Then call the routing learner pruning path during maintenance. Pruning is not automatic by default.

---

## Incident checklist

### Search returns nothing

1. Run `node cli/index.js doctor --no-semantic`.
2. Check FTS stats.
3. Run incremental reindex.
4. If still empty, run full reindex deliberately.
5. If semantic search is affected, rebuild Chroma collections.

### MCP server starts slowly

1. Check whether semantic prewarm is enabled.
2. If startup latency is unacceptable, set `L4_PREWARM=0`.
3. Expect the first semantic/hybrid query to pay lazy-load cost.

### Smart completion refuses work

1. Check `L4_DAILY_BUDGET_USD`.
2. Check cost stats for today's spend.
3. Raise the limit, set it to `0`, or wait for the daily window to roll over.

### Docs or install mismatch

Treat install docs as part of the release gate. If behavior changes, update:

- `README.md`
- `docs/INSTALL.md`
- `docs/guides/CONFIGURATION.md`
- this runbook
