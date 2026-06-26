# Session Log — P3: Guardrails & Ops Insurance

- **Date:** 2026-06-27
- **Author:** Evgen Kamenskih (@mergelord)
- **Area:** `claude-4layer-memory` hardening review (P3)

## Outcome

P3 was implemented and merged as a single PR (#72), on top of P2 (#71). All required CI checks were green at merge time.

## P3-1 — Guardrails

- **Reindex confirmation gate** — `reindex_memory(confirm=False)` is the default; without `confirm=True` it returns `{success: False, requires_confirmation: True, error: ...}` and does not rebuild. Existing reindex tests were updated to pass `confirm=True`; a new test covers the unconfirmed no-op path.
- **Input clamps** — `_clamp_limit` (1..`MAX_RESULT_LIMIT=100`, non-int -> default 10) and `_clamp_text` (trim to max chars, falsy -> "") applied in `search_memory`, `hybrid_search_memory`, and `smart_complete` (with `MAX_QUERY_CHARS=2000`, `MAX_TASK_CHARS=100000`, `MAX_CONTEXT_CHARS=200000`, `MAX_OUTPUT_TOKENS=8192`).
- **Daily budget cap** — `CostTracker.daily_budget_usd()` / `get_today_spend()` / `budget_status()`, driven by `L4_DAILY_BUDGET_USD` (default off / 0). `smart_complete` refuses to spend once the day's spend meets the cap (returns `{success: False, budget_exceeded: True, ...}`). The guard is skipped entirely when the env var is unset (no DB hit), so existing pricing tests are unaffected.
- **Routing history privacy + pruning** — `record_outcome` stores raw task text by default, but hashes it (`sha256:...`) when `ROUTING_STORE_TASK_TEXT=0`. New `prune_history(max_entries=None)` (env `ROUTING_HISTORY_MAX`, default 0 = off) deletes the oldest entries beyond the cap; it is not auto-invoked.

## P3-2 — Ops insurance

- **E2E MCP smoke test** (`tests/test_mcp_e2e_smoke.py`) — exercises every read-only tool (`get_memory_stats`, `search_memory`, `health_check`, the three cost tools) plus the unconfirmed-reindex no-op; asserts each returns a dict with a real bool `success`. No network, no mutation. `smart_complete` and the semantic backend are intentionally excluded.
- **Soak test** (`tests/test_soak.py`) — 300 sequential `search_memory` calls with FTS5 mocked; lenient timing bound.
- **Guardrail unit tests** (`tests/test_p3_guardrails.py`) — clamps, budget enable/exceed, routing privacy + prune.
- **`cm selftest` command** (`cli/index.js`, `cli/commands/selftest.js`) — local health check + FTS5 search smoke test, mirrors `cm doctor`, exits non-zero on failure.

## New environment flags

| Flag | Default | Effect |
| --- | --- | --- |
| `L4_DAILY_BUDGET_USD` | `0` (off) | Daily spend cap in USD; `smart_complete` refuses once reached. |
| `ROUTING_STORE_TASK_TEXT` | `1` | `0`/`false`/`no` stores a SHA-256 hash instead of raw task text. |
| `ROUTING_HISTORY_MAX` | `0` (off) | Max routing-history entries kept by `prune_history`. |

## Known follow-up: Python 3.14 CI matrix (NOT yet applied)

The planned non-blocking Python 3.14 matrix row edits `.github/workflows/test.yml`. The GitHub integration used in-session lacks the `workflows` permission, so workflow files cannot be pushed via the API (`403 Resource not accessible by integration`). Apply manually:

```yaml
    strategy:
      fail-fast: false
      matrix:
        os: [ubuntu-latest, windows-latest, macos-latest]
        python-version: ['3.10', '3.11', '3.12', '3.13']
        include:
          - os: ubuntu-latest
            python-version: '3.14'
            experimental: true

    runs-on:  matrix.os 
    continue-on-error:  matrix.experimental || false 
```

This is non-blocking by design (`experimental: true` + job-level `continue-on-error`), so it does not affect required checks. For normal matrix entries `matrix.experimental` is empty -> `false`, so they remain blocking.

## Constraints honored

- No data migration; all public contracts preserved.
- New behavior is opt-in via env vars and defaults to current behavior.
- CI kept green throughout.

## References

- PR #72 (P3): https://github.com/mergelord/claude-4layer-memory/pull/72
- PR #71 (P2), #70 (P1), #69 (P0): merged.
- VERSION: v1.6.0
