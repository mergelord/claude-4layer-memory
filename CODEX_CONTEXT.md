# Codex Persistent Context

## Invariants (never break these)

- `tests/test_memory_lint_helpers.py` — intentional mojibake fixtures, DO NOT modify encoding
- `scripts/__init__.py` — required by `tests/test_architecture.py`, DO NOT delete
- pylint must stay 10.00/10
- All tests must pass (currently 431, 1 skipped)
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

Pass criteria: 431 tests green, pylint no new errors, encoding clean.

## Recent Decisions

**2026-06-24/25** — PR #58: честный routing-тест, изоляция post-success bookkeeping в `smart_complete`, нормализация routing-скоров. Все 19 чеков зелёные.
- **Контекст:** подробное код-ревью `main`@`3d9016b` (состояние после PR #57) выявило три P2-фоллоуапа; реализованы в одной ветке по запросу пользователя.
- **Ветка/PR:** `fix/review-followups-routing-tests-smart-complete` от `main`@`3d9016b`; PR #58 (https://github.com/mergelord/claude-4layer-memory/pull/58). Коммиты: тест `test_routing_learner.py` (первый push), `08f9350` (`mcp_server.py` + `scripts/routing_learner.py`), `a952510` (lint `.items()`).
- **Фикс 1 — `tests/test_routing_learner.py` (честный поведенческий тест):** старый `test_success_history_prefers_model_over_failure` был ВАКУУМНЫМ — сидел 2 записи, но `predict_model` требует `history_count >= 3` (`if history_count < 3: return floor_model`), поэтому срабатывал cold-start и возвращался floor=`haiku`; ассерт проходил из-за floor, а НЕ из-за outcome-weighting. Переписан: 6 соседей (3× sonnet success, 3× opus failure), равная similarity (FakeCollection distance 0.2), равные счётчики (3 vs 3 — частота не решает), floor=haiku (не перекрывает) → `predict_model` обязан выбрать `sonnet` за счёт `OUTCOME_BONUS` vs `OUTCOME_PENALTY`. Добавлены зеркальный тест (opus success > sonnet failure) и `test_outcome_quality_beats_frequency` (haiku×5 провалов проигрывает sonnet×2 успехам — прямая проверка нормализации из фикса 3).
- **Фикс 2 — `mcp_server.smart_complete` (изоляция post-success bookkeeping):** расчёт стоимости (`resolve_price` + cache-тиры `CACHE_CREATION_PRICE_KEY`/`CACHE_READ_PRICE_KEY`) и `record_outcome` вынесены из основного `try` в отдельный `try/except`. Раньше сбой ПОСЛЕ успешного `complete()` (миссинг в price-таблице / ChromaDB-сбой) возвращал `{"success": False}` для фактически успешного ответа И писал ложный провал в learner → отравлял маршрутизацию. Теперь bookkeeping не может ни перевернуть успешный ответ, ни записать ложный negative. Семантика «пустой ответ → negative signal» (`was_successful = bool(result_text.strip())`) сохранена; в `except` основного try при реальной ошибке по-прежнему пишется `was_successful=False` (под защищённым inner try).
- **Фикс 3 — `routing_learner.predict_model` (нормализация `model_scores`):** раньше суммировались веса соседей по модели (`model_scores[m] += weight`) → побеждала самая ЧАСТАЯ модель, а не самая УСПЕШНАЯ. Теперь `model_weight_sums` + `model_counts`, затем `model_scores = {m: model_weight_sums[m] / model_counts[m]}` (среднее). Floor/tier-логика без изменений; существующие тесты `test_history_cannot_downgrade_below_floor` / `test_history_can_upgrade_above_floor` остаются зелёными (на сценариях с одной моделью среднее == сумме/1).
- **Lint (pylint C0206):** нормализующая comprehension сначала ловила `consider-using-dict-items` (итерация ключей + индексация того же dict), CI падал с exit code 16. Исправлено на `for model, weight_sum in model_weight_sums.items()`. Чистая lint-правка, поведение не меняется. Pylint снова 10.00/10.
- **CI:** после lint-фикса все 19 чеков зелёные — `lint.yml` (Pylint/MyPy/Ruff/EncodingGate/Bandit/Radon) + `test.yml` (ubuntu/windows/macos × Python 3.10–3.13).
- **Роль reviewer:** PR не мёржен автоматически — оставлено пользователю. Файлы PR: `tests/test_routing_learner.py`, `mcp_server.py`, `scripts/routing_learner.py`.
- This handoff entry is committed to `main` only.

**2026-06-24** — Зелёный CI: фикс Bandit B110 в `claude-4layer-memory`. Красным был не pytest, а **Code Quality / Bandit Security Check** (Failing after ~11s).
- **Диагноз:** `[B110:try_except_pass]` в `scripts/l4_semantic_global.py` (функция `_warn_if_mixed_metrics`): голый `except Exception: pass`. Bandit запускается с `-l` (`bandit -r scripts/ audit.py -l --skip B404,B603`), поэтому даже находка Severity Low даёт exit code 1.
- **Источник:** введён коммитом `90044c1` (semantic mixed-metrics), а НЕ `208fa77` (`fix(routing): context_len tokens`, трогает только `mcp_server.py` + `tests/test_estimate_complexity.py`, вне области Bandit). Ранняя ложная атрибуция исправлена — красный чек существовал ещё до `208fa77`.
- **Фикс (вариант А):** `except Exception:  # pylint: disable=broad-except` / `pass` → `except Exception as exc:  # pylint: disable=broad-except` / `logging.debug("metric check skipped: %s", exc)`. Тело `except` стало непустым → B110 уходит, диагностика метрик сохранена. Цель уникальна (второй `except Exception:` в начале файла идёт перед объявлением класса, без `pass`).
- **Ветка/коммит/PR:** `fix/bandit-b110-mixed-metrics` от `main`@`208fa77`; фикс-коммит `22c1611`; PR #54 (https://github.com/mergelord/claude-4layer-memory/pull/54). pre-edit blob `2bbc68b6`, post-edit blob `98d723cd` (size 27501).
- **Не задевает другие джобы:** правка только в `scripts/`, тесты её не касаются, pylint `W0718` (broad-except) уже отключён. Ruff/Pylint/MyPy/Pytest были зелёными — подтвердить на PR перед мёрджем, затем смёржить, и красный с `208fa77` уйдёт.
- **Долг по `208fa77` (вне этого PR):** `tests/test_estimate_complexity.py` — вакуумная тавтология (`if short == long: pass`), не покрывает изменённый путь `_approx_tokens`/`smart_complete`; мёртвые импорты `MagicMock, patch`; `prompt_tokens_approx` всё ещё word-based. Переписать только по запросу.
- This handoff entry is committed to `main` only.

**2026-06-23** — Code review of fix plan P1–P3 (cost tracking / FTS5 sanitizer / routing learner), reviewed against actual file contents at HEAD `60a4d6ed`. Plan is mostly correct, but the following must be fixed BEFORE any PR. Review delivered; PR not yet built (awaiting user choice: build feature branch + PR vs. inline GitHub review comments).
- **P1 (prefix-match in `scripts/cost_tracker.py` `resolve_price`) — RUNTIME BLOCKER:** `logging` is NOT imported in `cost_tracker.py` (imports: argparse, codecs, sys, sqlite3, json, os, tempfile, time, pathlib, datetime, typing, contextlib). The planned `logging.warning(...)` → `NameError`. Fix: add `import logging` (+ `logger = logging.getLogger(__name__)`) OR use `print(..., file=sys.stderr)` to match the existing `_load_prices` style. The prefix-match `sorted(self.prices, key=len, reverse=True)` is correct (longest key first → no shadowing of `claude-opus-4` by a future `claude-opus-4-1`). `_resolve_price = resolve_price` alias preserved.
- **P1 test coverage — LOGIC ERROR:** the planned integration test in `tests/test_mcp_server.py` (mock `tracked_claude.complete` to return a versioned model) does NOT catch the bug. It bypasses `track_claude_message` (the ledger path where the mispricing actually lives) and uses the SHORT alias `chosen_model`, which was already priced correctly pre-fix — proof: existing `test_smart_complete_prices_opus_at_real_rate_not_haiku` is green WITHOUT the fix. The real regression must call `tracker.track_claude_message(...)` with a fake message whose `.model = "claude-opus-4-20250514"` (+ `.usage`) and assert `total_cost == pytest.approx(15.0)` per 1M input tokens (Opus rate, not the Sonnet fallback). Put it in `tests/test_cost_tracker.py`.
- **P2.2 (`record_outcome` on exception in `mcp_server.py` `smart_complete`) — RUNTIME BLOCKER:** `chosen_model` is assigned INSIDE the `try`, at the `routing_learner.predict_model(...)` line, which can itself raise (`predict_model` → `_encode` → `RuntimeError` if `sentence_transformers` is missing). The planned `if chosen_model:` in the `except` then raises `UnboundLocalError`, masking the real error. Fix: initialize `chosen_model: str | None = None` BEFORE the `try`. The `record_outcome(...)` kwargs were validated against `routing_learner.record_outcome` signature — correct.
- **P3.2 (`pytest.approx` in `tests/test_mcp_server.py`) — RUNTIME BLOCKER:** `pytest` is NOT imported in `test_mcp_server.py` (imports: sys, Path, SimpleNamespace, patch). `pytest.approx` → `NameError`. Fix: add `import pytest`.
- **P2.3-A — FACTUAL CORRECTION:** the user's premise (“comment is correct after the cycle fix, don't touch”) is WRONG. The comment in `scripts/l4_bm25_search.py` (“both lexical engines import from `ranking`; neither imports the other”) contradicts the `ranking.py` docstring (“`l4_fts5_search` already imports `l4_bm25_search`”). `l4_fts5_search` DOES import `l4_bm25_search` (one-directional). Reword the comment (e.g. “neither imports the sanitizer from the other”) instead of skipping it.
- **Minor:** mypy CI will flag the `resolve_price(None)` test against the `model: str` signature → change signature to `model: Optional[str]` (`Optional` already imported). P2.1 docstring note is fine. P2.3-B stale-docstring fix (`l4_fts5_search.sanitize_fts5_query` → `ranking.sanitize_fts5_query`, `tests/test_l4_bm25_search.py` ~line 52) is correct.
- **Confirmed correct / deferred:** P3.1 (sanitizer refactor), P3.3 (context_len word-vs-token), P3.4 (`_resolve_price` alias) deferrals are fine. Work order accepted: P1+tests → P2.2/P2.1/P2.3-B → P3.2 → pytest → ruff+pylint → commit/feature-branch/push/PR.
- **File SHAs at HEAD `60a4d6ed` (for safe `create_or_update_file` updates):** `scripts/cost_tracker.py` `e3620476`, `mcp_server.py` `19ad5fb0`, `scripts/routing_learner.py` `5f155f38`, `scripts/ranking.py` `dedc401b`, `scripts/l4_bm25_search.py` `d5430111`, `tests/test_l4_bm25_search.py` `09db609b`, `tests/test_mcp_server.py` `2e271c6c`, `tests/test_cost_tracker.py` `6f8c1c74`.
- **NEXT:** if building the PR, incorporate all six corrections above (`import logging`, `chosen_model = None` before try, `import pytest`, regression on `track_claude_message` with versioned id, reword P2.3-A comment, `Optional[str]` signature). This handoff entry is committed to `main` only.

**2026-05-30** — Working agreement + GitHub workflow-write limitation:
- AGENT COMMUNICATION RULE (per user request): before creating or changing any config that requires special access/permissions or new connections (e.g. CI/workflow files, tokens, integrations), explain UP FRONT *why* it is needed and *what* access/setup the user must provide — do NOT surface this only after hitting an error mid-task.
- GitHub workflow-file writes are BLOCKED via the hosted Notion GitHub MCP connector (api.githubcopilot.com): writing `.github/workflows/*.yml` returns `403 Resource not accessible by integration`, while normal file writes (code/docs/CODEX_CONTEXT.md) work fine. Root cause: the hosted connector authenticates via its own OAuth app (fixed scopes, no workflow-write) and IGNORES any user PAT — so adding `repo`+`workflow` to a classic token does NOT help, and registering a custom OAuth app does NOT help either.
- Running CI is unaffected: pushing code / opening PRs still auto-triggers existing workflows (no special scope needed). Only EDITING workflow definitions is blocked.
- Workarounds: (1) user commits `.github/workflows/*` manually (agent supplies exact YAML), or (2) run a self-hosted token-based GitHub MCP server (`GITHUB_PERSONAL_ACCESS_TOKEN` with repo+workflow) and connect THAT instead of the hosted connector.
- Note: an extra (3rd) "GitHub" connector was created while trying the PAT route; it did not help and can be removed in Notion integration settings.
- The intended (still un-applied) `test.yml` change is a ratchetable coverage floor: replace the `Run pytest` step `pytest tests/ -v --tb=short` with `pytest tests/ -v --tb=short --cov=. --cov-report=term-missing --cov-fail-under=0` (raise the floor as coverage improves). It is optional — PR/CI/merge all work without it.

**2026-05-30** — Code review hardening branch (`fix/code-review-hardening`):
- Created branch `fix/code-review-hardening` off `main` (`417e9f1`); 7 commits, **no PR opened yet** (PR deferred per user — record context only for now).
- In-process hybrid semantic search: `scripts/l4_fts5_search.py` no longer shells out to `l4_semantic_global.py search-all` on every query (which reloaded sentence-transformers + ChromaDB each time and risked a 30s timeout). Now reuses a single cached `GlobalSemanticMemory` via `_get_semantic_memory()` (lru-cached) and normalises results to the documented `{key,text,distance,metadata,source}` contract (drops `id`/`_chunks`). Added an importable `hybrid_search()` so the MCP server can consume the fused ranking directly (previously only the CLI printed it).
- MCP server hardening: `mcp_server.py` module-level component init is guarded so import never crashes when the DB is locked/unavailable; added a `hybrid_search_memory` tool exposing the full FTS5+semantic+BM25+RRF+rerank pipeline (previously only raw FTS5 was exposed).
- Dependencies: pinned upper bounds in `requirements*.txt` to prevent silent dependency drift.
- `package.json`: `npm test` no longer fails — it now points to the Python test suite.
- `install.sh`: copies ALL `scripts/*.py` (hybrid loads `l4_semantic_global` next to `l4_fts5_search`); fixed the stale "Python 3.7+" prompt to 3.10+.
- `.github/workflows/test.yml`: coverage measured with an enforced (ratchetable) floor.
- README: replaced static/inaccurate shields.io badges with live Actions workflow badges (`lint.yml`, `test.yml`); dropped the unverified "(10.0/10)" and "MyPy strict mode" claims that CI does not enforce.
- Tests: replaced the subprocess-based hybrid semantic test with in-process tests (monkeypatch `_get_semantic_memory`: `None` and raising engines degrade to `[]`, real hits normalise to the documented contract); added `hybrid_search()` return-contract tests (RETURNS merged ranking, `[]` when no engine hits) and an MCP `hybrid_search_memory` wrapper smoke + failure test.
- Branch commits (newest→oldest): `2c98f28`, `3485fb9`, `2b266bf`, `d0c776d`, `a3fb41`, `e7225f5`, `d3980689`.
- NEXT STEPS: (1) re-run full gates on the branch before opening the PR — pytest, pylint 10.00, ruff, mypy, bandit, encoding scan (see Test Protocol + CLAUDE.md "Full PR Validation"); (2) open PR `fix/code-review-hardening` → `main`; (3) after merge, the last open audit item is AUDIT #11 (repo junk / packaging cleanup).
- This handoff entry is committed to `main` only — intentionally kept out of the feature branch so it does not pollute the PR review diff.

**2026-05-29** - Stop hook skipped-project guard:
- Fixed `hooks/stop_handoff_universal.py` so `main()` exits cleanly when `detect_project()` returns `None` for system/blacklisted paths, instead of building `.claude\projects\None` paths.
- Added regression coverage in `tests/test_hooks_encoding_gate.py`.
- Validation: focused hook tests `10 passed`; full pytest `431 passed, 1 skipped`; encoding gate clean; `py_compile` clean for the touched hook/test files.
- Committed and pushed to GitHub/GitLab as `796cf33 fix: skip stop hook when project detection fails`; synced live `C:\Users\MYRIG\.claude\hooks\stop_handoff_universal.py`. Backup: `C:\Users\MYRIG\.claude\backups\stop_handoff_universal.py.codex_20260529_none_project_guard.bak`. Repo/live hashes match and live `py_compile` passed.

**2026-05-29** - Git-clone-only install docs:
- README already had the top-level warning that the project is git-clone-only and not published to npm, but `cli/README.md` still recommended `npm install -g claude-memory-cli` / `npm install claude-memory-cli`.
- Updated `cli/README.md` to document only the clone + `npm install` / optional `npm link` flow and changed the CI snippet to run from the cloned repo with `node cli/index.js`.
- Aligned `README.md` visible version badge/text with `VERSION` and `package.json`: `1.5.1`.
- Validation: encoding gate clean; no remaining registry-install recommendations in `README.md` / `cli/README.md`.

**Architecture:**
- `.claude\` = runtime memory + hooks, NOT full installation
- Node CLI runs from repo only (`C:\BAT\claude-4layer-memory`)
- `node_modules` not installed in `.claude`
