# Production Readiness

Status: **P4 production-readiness hardening in progress**  
Baseline: `v1.6.0`, after P0-P3 hardening and the non-blocking Python 3.14 CI row.

This document defines what "production ready" means for this repository and how to verify it before tagging a release.

---

## Current readiness snapshot

### Already in place

- Health/readiness surface:
  - `cm doctor`
  - MCP `health_check`
  - structured component statuses: FTS5, semantic backend, routing learner, cost ledger, host facts
- Local operational smoke test:
  - `cm selftest`
  - health check + FTS5 smoke test
- Search hardening:
  - FTS5 keyword search
  - hybrid search with FTS5 + semantic + BM25 + RRF
  - optional reranking
  - debug timing metadata for hybrid MCP calls
- Reindex safety:
  - destructive full reindex requires `confirm=True`
  - default call is a no-op that returns `requires_confirmation: true`
- Input guardrails:
  - result limit clamp: `1..100`
  - query/task/context/output-token caps for MCP tools
- Cost guardrails:
  - optional daily budget via `L4_DAILY_BUDGET_USD`
  - default is off / no behavior change
- Privacy guardrails:
  - optional routing task-text hashing via `ROUTING_STORE_TASK_TEXT=0`
  - optional routing-history pruning via `ROUTING_HISTORY_MAX`
- Dependency reproducibility:
  - `constraints.txt` defines the runtime baseline
  - install scripts use `pip install -r requirements.txt -c constraints.txt`
  - docs recommend the same reproducible install path
- CI coverage:
  - Python tests on Linux, Windows, macOS for Python 3.10-3.13
  - Python 3.14 experimental on Linux, non-blocking
  - lint, type-check, ruff, encoding gate, bandit, radon, shellcheck

### Remaining production-readiness risks

| Area | Risk | Required before final production stamp |
| --- | --- | --- |
| Packaging | Project is git-clone install only; npm package is intentionally disabled. | Keep README/install docs explicit and avoid claiming registry install support. |
| CI dependency reproducibility | Installers enforce `constraints.txt`, but CI workflow install steps still use unconstrained `requirements*.txt`. | Wire `-c constraints.txt` into test/lint workflows when workflow-file edits are available. |
| Runtime docs drift | Older docs may still reference Python 3.7 or incomplete env flags. | Keep install/config/operations docs aligned with Python 3.10+ and P3 env flags. |
| Workflow maintainability | Test workflow is expanded into explicit jobs to avoid expression-copy issues. | Accept verbosity or later restore a matrix in a workflow-authorized commit. |
| Release evidence | Releases should include a repeatable manual verification checklist. | Use the release gate below before tagging. |

---

## Release gate

A release can be tagged as production-ready only after all required gates pass.

### 1. Clean working state

```bash
git status --short
```

Expected: no unintended local changes.

### 2. Install dependencies

Recommended reproducible install:

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt -c constraints.txt
python -m pip install -r requirements-dev.txt
```

If constraints are not used, record that explicitly in release notes.

### 3. Test suite

```bash
python -m pytest tests/ -v --tb=short
```

Expected: pass on supported Python versions.

### 4. Static quality checks

```bash
python -m pylint scripts/*.py audit.py \
  --disable=C0114,C0115,C0116,R0913,R0914,R0915,R0903,R0904,W0718,R1702,C0415,R0902,R0912,R0801 \
  --max-line-length=110 \
  --good-names=i,j,k,e,f,_,rc

python -m mypy scripts/ audit.py \
  --explicit-package-bases \
  --ignore-missing-imports \
  --no-strict-optional \
  --allow-untyped-defs \
  --allow-incomplete-defs

ruff check scripts/*.py audit.py
bandit -r scripts/ audit.py -l --skip B404,B603
radon cc scripts/*.py audit.py -a -nb
radon mi scripts/*.py audit.py -nb
python scripts/scan_repo_encoding.py
```

Expected: all pass.

### 5. Operational self-test

```bash
node cli/index.js selftest --no-semantic
node cli/index.js doctor --no-semantic
```

If semantic dependencies and local model cache are available:

```bash
node cli/index.js selftest
node cli/index.js doctor
```

Expected:

- `selftest` exits with code `0`
- `doctor` reports overall status `ok` or an understood `degraded`, not `down`

### 6. MCP smoke surface

At minimum verify these tools return dictionaries with a real boolean `success` field:

- `search_memory`
- `hybrid_search_memory`
- `get_memory_stats`
- `get_cost_stats`
- `get_recent_cost_operations`
- `get_cost_breakdown`
- `health_check`
- `reindex_memory(confirm=False)`

Expected: read-only tools do not mutate state; unconfirmed reindex is a no-op.

### 7. Guardrail regression checks

```bash
python -m pytest tests/test_p3_guardrails.py tests/test_mcp_e2e_smoke.py tests/test_soak.py -v --tb=short
```

Expected:

- input clamps work
- budget guard works when enabled
- routing privacy hash mode works
- history pruning works
- unconfirmed reindex remains blocked
- soak test remains within the soft timing boundary

### 8. Documentation check

Before release, verify these docs agree with the current behavior:

- `README.md`
- `docs/INSTALL.md`
- `docs/guides/CONFIGURATION.md`
- `docs/OPERATIONS.md`
- `MCP_SERVER.md`
- `CHANGELOG.md`

---

## Supported runtime baseline

- Python: **3.10+**
- CI blocking versions: **3.10, 3.11, 3.12, 3.13**
- CI experimental version: **3.14 on Ubuntu**, non-blocking
- Node.js for CLI wrapper: **14+**
- Install mode: **git clone only**
- npm registry install: **not supported**

---

## Production-ready definition

For this project, production-ready means:

1. Fresh clone can install and run the documented smoke checks.
2. Existing users can upgrade without silent data migration or destructive defaults.
3. Destructive operations require explicit confirmation.
4. Expensive operations have optional hard budget protection.
5. Privacy-sensitive routing history can avoid storing raw task text.
6. Health, logs, and self-test give enough signal to debug local installs.
7. CI covers supported OS/Python combinations.
8. Docs are accurate about install mode, supported versions, and env flags.
