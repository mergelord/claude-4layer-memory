# Codex Persistent Context

## Invariants (never break these)

- `tests/test_memory_lint_helpers.py` — intentional mojibake fixtures, DO NOT modify encoding
- `scripts/__init__.py` — required by `tests/test_architecture.py`, DO NOT delete
- pylint must stay 10.00/10
- All tests must pass (currently 358, 1 skipped)
- No `git commit --no-verify` to bypass pre-commit hooks

## Python Interpreter

```
C:\Program Files\Python313\python.exe
```

or `py -3.13`

## Test Protocol (run after every patch)

```powershell
# Mandatory
py -3.13 -m pytest tests/ -q

# If touching scripts/*.py:
py -3.13 -m pylint scripts/*.py audit.py `
  --disable=C0114,C0115,C0116,R0913,R0914,R0915,R0903,R0904,W0718,R1702,C0415,R0902,R0912,R0801 `
  --max-line-length=110 --good-names=i,j,k,e,f,_,rc

# If touching encoding-related code:
py -3.13 scripts/scan_repo_encoding.py
```

Pass criteria: 358 tests green, pylint no new errors, encoding clean.

## Recent Decisions

**2026-05-27** — semantic CLI contracts + UTF-8 + lazy load patch (commit 065cc24, ec53a22):
- Collection normalization: `C--BAT` → `C__BAT` via `_COLLECTION_NON_ALNUM.sub("_", name)`
- Resolver tries exact match first, then prefix match `memory_C__BAT*`
- `_print_results` fallback: `r.get("key", make_join_key(source, file))`
- UTF-8 init: `str(getattr(stream, "encoding", None) or "").lower()` — str() cast required for pylint
- Lazy SentenceTransformer: loaded only at search/index, raises `RuntimeError` if missing
- Lazy l4_rerank: imported only on hybrid rerank path via `@lru_cache`

**Architecture:**
- `.claude\` = runtime memory + hooks, NOT full installation
- Node CLI runs from repo only (`C:\BAT\claude-4layer-memory`)
- `node_modules` not installed in `.claude`
