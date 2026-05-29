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

**2026-05-29** - Live `.claude` runtime sync from GitHub:
- Used clean deploy worktree `C:\tmp\claude-4layer-memory-deploy-main` at `origin/main` `5afd331`; local repo remained dirty/behind and was not merged.
- Synced GitHub runtime deltas into `C:\Users\MYRIG\.claude\hooks` and `C:\Users\MYRIG\.claude\scripts`: `cost_tracker.py`, `l4_fts5_search.py`, `l4_semantic_global.py`. Backup: `C:\Users\MYRIG\.claude\backups\github-sync-20260529_063535`.
- Runtime checks passed for cost tracker stats, FTS5 stats, semantic stats, active SessionStart hooks, `auto-remember.py`, `semantic_search.py`, Stop wrapper, and PreCompact after hotfix.
- Live-only hotfix: `precompact-flush-l4.py` now calls `GlobalSemanticMemory.index_all()` with fallback to old `index_global_memory()`/`index_project()` methods. Upstream this or future syncs can overwrite it.
- `crash-recovery.py` passed isolated temp-USERPROFILE smoke. Live run was intentionally skipped because preflight found one real candidate (`C--BAT`, session `1e37c274-13ef-4c26-8209-4b5c7b520c88`) and full run would append to real `handoff.md`.
- Follow-up after repo fast-forward/tag `v1.5.0` (`origin/main` `d070702`): only additional live runtime delta was `scripts/l4_fts5_search.py` from PR #39/AUDIT #5 first slice. Updated live copies in `.claude\hooks` and `.claude\scripts`; backup `C:\Users\MYRIG\.claude\backups\github-sync-20260529_085823-v150`; SHA256/py_compile/stats/search smoke passed.

**2026-05-29** - DSM Telegram monitor:
- Added `scripts/dsm_telegram_monitor.py`: stdlib-only SSH monitor for DSM/codex-lab with Telegram Bot API notifications. Commands: `status`, `status --send`, `check`, `watch`, `test-telegram`.
- Added ignored local config flow via `config/dsm_telegram_monitor.example.json`; real configs should be copied to `config/*.local.json` or supplied with `DSM_*` environment variables.
- Added docs in `docs/DSM_TELEGRAM_MONITOR.md` and tests in `tests/test_dsm_telegram_monitor.py`.
- Validation after patch: focused monitor tests `8 passed`; full pytest `382 passed, 1 skipped`; pylint `10.00/10`. Pylint still logs non-fatal cache write warning under `%LOCALAPPDATA%`.

**2026-05-29** - Codex-lab project upload and validation:
- Uploaded local archive `.codex-temp\claude-4layer-memory.tar.gz` to DSM path `/volume1/docker/codex-lab/cache/upload/claude-4layer-memory.tar.gz`. Used `ssh ... cat > file` because Synology SFTP/scp failed; verified SHA256 `582c81e6509f2b01cde050827647aef504674a2ee36b79eb51e1efe44e204c74`.
- Extracted project to `/volume1/docker/codex-lab/workspace/claude-4layer-memory`; inside container this is `/workspace/claude-4layer-memory`. Added Git `safe.directory` for that path inside `codex-lab`.
- Created Python venv `/cache/venvs/claude-4layer-memory`; installed `requirements-dev.txt` and `requirements.txt`. Venv is about `5.5G` because Linux `torch` pulled CUDA wheels; `/volume1` still has about `1.4T` free.
- Codex-lab validation results: `python -m pytest tests/ --tb=short -q` -> `374 passed, 1 skipped in 47.87s`; `python scripts/scan_repo_encoding.py` -> `150 file(s) scanned, all clean`; project pylint command -> `10.00/10`.
- Node validation: `npm ci --cache /cache/npm --prefer-offline` -> `0 vulnerabilities`; `node cli/index.js --version` -> `1.4.0`; `node cli/index.js --help` works.
- Uploaded project mirrors local dirty tree: `.gitignore` and `CODEX_CONTEXT.md` modified; untracked `docs/CODEX_REVIEW_MR32_GITLAB_CI.md` and `docs/RESEARCH_MR32_RESULT.md`.

**2026-05-29** — Codex-lab handoff before restart:
- User may restart Codex because modem connection is unstable; resume from this context instead of re-discovering DSM state.
- Working DSM SSH command uses key `C:\tmp\codex_dsm_myrig_key2` with `-p 22756 -o BatchMode=yes -o ConnectTimeout=10 -o UserKnownHostsFile=.codex-temp\dsm_known_hosts -o StrictHostKeyChecking=yes -i C:\tmp\codex_dsm_myrig_key2 jbsergie@31.10.124.45`.
- `codex-lab` has already been verified live on DSM: container status `running` / Docker ps `Up`, image `node:22-bookworm-slim`, restart `unless-stopped`, memory limit `4294967296`, security opt `no-new-privileges:true`.
- Verified binds: `/volume1/docker/codex-lab/workspace:/workspace`, `/volume1/docker/codex-lab/cache:/cache`, `/volume1/docker/codex-lab/logs:/logs`, `/volume1/docker/codex-lab/bin:/usr/local/codex-lab/bin:ro`.
- Verified inside container: Python `3.11.2`, Node `v22.22.3`, npm/npx `10.9.8`, Git `2.39.5`, ripgrep `13.0.0`, curl `7.88.1`; `/var/run/docker.sock` absent.
- Host dirs exist and are owned by `jbsergie users`: `/volume1/docker/codex-lab`, `workspace`, `cache`, `logs`, `bin`.
- No repo code changed for codex-lab verification; tests not run because only context/ops notes were touched.

**2026-05-28** — DSM/Synology automation context:
- DSM host: `31.10.124.45:22756`, SSH user `jbsergie`.
- Codex SSH key is already authorized on DSM; user PuTTY key `jbsergie-putty` was added to `/var/services/homes/jbsergie/.ssh/authorized_keys`.
- `jbsergie` has persistent passwordless sudo via `/etc/sudoers.d/codex-admin` (`jbsergie ALL=(ALL) NOPASSWD: ALL`).
- Docker on DSM works via `/usr/local/bin/docker`; host is Synology DS425+ class (`synology_geminilakenk_ds425+`), Docker server `24.0.2`.
- GitLab runner experiment was abandoned because GitLab.com required account verification (phone/card/captcha). Runner was unregistered from GitLab, container `gitlab-runner` was removed, `/volume1/docker/gitlab-runner` was deleted, images `gitlab/gitlab-runner:alpine` and `python:3.11-slim` were removed.
- `codex-lab` is deployed on DSM under `/volume1/docker/codex-lab` with host dirs `workspace`, `cache`, `logs`, and `bin`; it intentionally does not mount `/var/run/docker.sock` or `.claude` runtime memory paths.
- Current `codex-lab` container: image `node:22-bookworm-slim`, restart `unless-stopped`, memory limit `4g`, security option `no-new-privileges:true`, binds `/workspace`, `/cache`, `/logs`, `/usr/local/codex-lab/bin:ro`.
- Verified tools inside `codex-lab`: Python `3.11.2`, Node `v22.22.3`, npm/npx `10.9.8`, Git `2.39.5`, ripgrep `13.0.0`, curl `7.88.1`; Docker socket absent.
- The first `ubuntu:24.04` attempt was removed because `apt install npm` dragged in Debian node packages and `dpkg` stalled during unpack. The persistent host volume was kept; only the container was replaced.
- Current DSM Docker state: `codex-lab` is `Up`; pre-existing `linuxserver-firefox-1-1` remains in `Created` status.

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
