# Codex Persistent Context

## Invariants (never break these)

- `tests/test_memory_lint_helpers.py` — intentional mojibake fixtures, DO NOT modify encoding
- `scripts/__init__.py` — required by `tests/test_architecture.py`, DO NOT delete
- pylint must stay 10.00/10
- All tests must pass (currently 374, 1 skipped)
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

Pass criteria: 374 tests green, pylint no new errors, encoding clean.

## Recent Decisions

**2026-05-27** — Housekeeping closed (all prior PR blockers resolved):
- Bug N-4 (RRF basename collision, silent correctness) fixed: `ranking.normalize_document_path` + `make_join_key` POSIX rel_path; FTS5/BM25/semantic all use document-level rel_path keys. Regression test added in `test_key_contract.py`. **After merge: `l4_search.bat reindex` + rebuild ChromaDB.**
- `.pytest-tmp-codex-review/` deleted and added to `.gitignore`; `scan_repo_encoding.py` now clean on full repo.
- `docs/CODE_REVIEW_REPORT.md`: C-1 marked ✅ ИСПРАВЛЕНО (resolved 2026-05-27); N-4 documented as resolved.
- `CLAUDE.md` synced to 1.4.0 / 2026-05-27; added "Full PR Validation" section (pytest, encoding scan, ruff, mypy, full pylint when scripts/*.py touched, node --check when cli/*.js touched).
- `requirements-dev.txt`: duplicate `pytest-cov` removed, `black`/`flake8` dropped, added `ruff`, `pylint`, `bandit`, `radon`, `vulture`.
- Gates after housekeeping: pytest `374 passed, 1 skipped`; pylint -E clean on 6 critical modules; `scan_repo_encoding` clean on whole repo.

**2026-05-27** — Codex independent review findings folded into `docs/CODE_REVIEW_REPORT.md`; transient `docs/CODEX_REVIEW_V1_4_0.md` was not committed (intermediate snapshot, made stale by housekeeping fixes — risk of confusion in PR).

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
