# claude-4layer-memory Codex Instructions

## Project Role

Review this repository as a Windows-first Python memory system with deployed runtime files under `C:\Users\MYRIG\.claude`.

Primary role: reviewer. Implement only when explicitly asked.

## Required Runtime Invariants

- Local repository: `C:\BAT\claude-4layer-memory`.
- Deployed runtime: `C:\Users\MYRIG\.claude`.
- Runtime memory/data must not be overwritten during code sync:
  - `C:\Users\MYRIG\.claude\memory`
  - `C:\Users\MYRIG\.claude\projects`
  - `C:\Users\MYRIG\.claude\semantic_db_global`
  - `C:\Users\MYRIG\.claude\memory_fts5.db`
  - sessions, history, cache, and settings unless explicitly requested.
- Python hooks in `.claude` run through `C:\Program Files\Python313\python.exe`.
- Node CLI dependencies are not installed in `.claude`; Node CLI is expected to run from this repository.

## CI Commands

Use the exact CI flags when checking locally.

Pylint:

```powershell
& "C:\Program Files\Python313\python.exe" -m pylint scripts/*.py audit.py `
  --disable=C0114,C0115,C0116,R0913,R0914,R0915,R0903,R0904,W0718,R1702,C0415,R0902,R0912,R0801 `
  --max-line-length=110 `
  --good-names=i,j,k,e,f,_,rc
```

Pytest:

```powershell
& "C:\Program Files\Python313\python.exe" -m pytest tests/ --tb=short -q
```

Encoding gate:

```powershell
& "C:\Program Files\Python313\python.exe" scripts\scan_repo_encoding.py
```

## Critical Contracts

- `scripts/l4_semantic_global.py` must support:
  - `stats`
  - `index-all`
  - `cleanup`
  - `cleanup --dry-run` without deleting collections
  - `search`
  - `search-all`
  - `search-global`
  - `search-project <project> <query>`
- `search-global` must search only global memory.
- `search-project` must search only the requested project and must not include the project name in the query text.
- Semantic search hook integration must use JSON output for machine parsing. Do not depend on human-readable markers as the contract.
- `index_directory()` must remain idempotent; use update/upsert semantics rather than duplicate add-only writes.
- Deployed hook scripts must have all sibling imports copied into `.claude\hooks`.

## Files And Fixtures

- Do not "repair" intentional mojibake fixtures in tests or docs without checking their purpose.
- `scripts/__init__.py` is intentional and may be required by architecture/import tests.
- Keep `package.json`, `VERSION`, and README version references aligned.

## Review Focus

Prioritize:

- broken installs or deployed runtime behavior
- missing dependencies in `.claude\hooks`
- mismatched Python interpreter usage
- CI failures caused by exact workflow flags
- command-line contract regressions
- unsafe cleanup/delete behavior
- changes to shared modules without tests

Avoid broad rewrites and style-only changes.

## Quality Bar

- pylint must stay **10.00/10** — project invariant, not a target
- All tests must pass (currently 358)
- Pre-commit hook runs automatically: Memory Lint + architecture tests + EncodingGate

## Persistent Context

Read `CODEX_CONTEXT.md` before any patch. Update "Recent decisions" after significant changes.
