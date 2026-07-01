# MemoryLinter Split Design

## Status

Design proposal for Issue #11: `Integrate memory_lint_helpers.py during MemoryLinter split`.

This document does not change the public `memory_lint.py` CLI surface. It defines the target architecture and migration sequence for splitting the monolithic `MemoryLint` class into focused modules while preserving current behavior.

## Background

`scripts/memory_lint.py` currently owns several responsibilities:

- CLI argument parsing and exit-code orchestration
- Layer 1 deterministic checks
- Layer 2 semantic/heuristic checks
- pre-delivery checklist orchestration
- encoding validation and mojibake repair commands
- file discovery, cached reads, frontmatter parsing, and markdown link parsing
- reporting and output formatting through `BaseReporter`

`scripts/memory_lint_helpers.py` already contains reusable helpers:

- `RegexPatterns`
- `CheckResultHandler`
- `SafeFileOperations`
- `FrontmatterExtractor`
- `ValidationHelpers`
- `EncodingGate`
- `EncodingError`

Today, `EncodingGate` is production code and is already imported by `memory_lint.py`. The other helpers are still mostly preparatory. This keeps Issue #11 open and leaves duplicated helper logic inside `MemoryLint`.

## Goals

- Keep `memory_lint.py` as the stable CLI entrypoint.
- Move reusable helper logic out of `MemoryLint` and into focused modules.
- Make `memory_lint_helpers.py` fully production-consumed instead of partially preparatory.
- Preserve the existing CLI contract:
  - `--layer`
  - `--quick`
  - `--checklist`
  - `--report`
  - `--validate-encoding`
  - `--repair-mojibake`
  - `--apply`
- Preserve current exit-code behavior.
- Keep changes incremental and easy to review.

## Non-goals

- No change to public command names or flags.
- No rewrite of checker registries already split into `consistency_checkers.py` and `antipattern_checkers.py`.
- No package publishing change.
- No semantic behavior changes unless covered by explicit regression tests.

## Proposed module shape

### `scripts/memory_lint.py`

Remains the CLI entrypoint.

Responsibilities after split:

- parse CLI args
- resolve memory path
- dispatch to encoding operations, checklist, or lint layers
- translate result objects into process exit codes

Target size: small orchestration layer only.

### `scripts/memory_lint_core.py`

Owns the `MemoryLint` orchestration class.

Responsibilities:

- load config
- coordinate Layer 1 and Layer 2 checks
- own lifecycle-level methods such as `run_layer1`, `run_layer2`, `generate_report`, and `clear_cache`
- depend on smaller checker/helper modules

### `scripts/memory_lint_layer1.py`

Owns deterministic checks.

Candidate functions/classes:

- ghost links
- orphan files
- duplicate titles
- HOT age
- WARM age
- file sizes
- project publication status

### `scripts/memory_lint_layer2.py`

Owns semantic and heuristic checks.

Candidate functions/classes:

- contradiction prompt construction
- outdated claims
- consistency registry integration
- completeness markers
- anti-pattern registry integration

### `scripts/memory_lint_checklist.py`

Owns pre-delivery checklist composition.

Candidate functions/classes:

- no duplicate memories
- all links valid
- frontmatter complete
- HOT memory fresh
- WARM memory fresh
- file sizes OK
- Why/How sections present

### `scripts/memory_lint_encoding.py`

Optional thin wrapper around encoding CLI operations.

Candidate functions/classes:

- `_safe_rglob_md`
- validate encoding command
- repair mojibake command
- repair summary printing

This module should continue to import `EncodingGate` from `memory_lint_helpers.py`.

### `scripts/memory_lint_helpers.py`

Production helper module.

Target role:

- `RegexPatterns`: common compiled regexes consumed by link/frontmatter/date extraction
- `SafeFileOperations`: shared safe read/stat helpers
- `FrontmatterExtractor`: canonical frontmatter and link extraction helper
- `ValidationHelpers`: reusable field validation and date extraction helpers
- `CheckResultHandler`: optional reporting helper for check result formatting
- `EncodingGate` / `EncodingError`: production encoding guard and cleanup utilities

Once at least the parser/file helpers are wired into production modules, remove the "preparatory" language from the module docstring and update `__all__` to reflect the actual public surface.

## Migration plan

### Phase 1 — design and guardrails

- Add this design document.
- Keep runtime behavior unchanged.
- Use this document as the reviewable architectural decision for Issue #11.

### Phase 2 — helper integration without moving checks

Low-risk production change:

- Replace `MemoryLint.extract_links()` implementation with `FrontmatterExtractor.extract_links()`.
- Replace `MemoryLint._extract_frontmatter()` implementation with `FrontmatterExtractor.extract_frontmatter()`.
- Replace local date regex usage with `ValidationHelpers.extract_dates()` where appropriate.
- Introduce `SafeFileOperations` for safe reads/stats inside `MemoryLint`.
- Keep method names on `MemoryLint` for compatibility with existing tests.

Expected result:

- `memory_lint_helpers.py` is no longer mostly preparatory.
- Issue #11 acceptance criteria starts to be satisfied without large file movement.

### Phase 3 — split encoding CLI operations

- Move `_safe_rglob_md`, `_run_encoding_validation`, `_run_encoding_repair`, and repair helper functions into `memory_lint_encoding.py`.
- Keep imported wrappers in `memory_lint.py` if needed for backward-compatible tests.
- Add focused tests for the new module.

### Phase 4 — split Layer 1 deterministic checks

- Extract deterministic checks into `memory_lint_layer1.py`.
- Keep `MemoryLint.run_layer1()` as orchestration.
- Preserve output text where tests depend on it.
- Add regression tests for path traversal, unreadable files, and config thresholds.

### Phase 5 — split Layer 2 and checklist

- Extract Layer 2 checks into `memory_lint_layer2.py`.
- Extract pre-delivery checklist into `memory_lint_checklist.py`.
- Keep `memory_lint.py --checklist` behavior unchanged.

## Test strategy

Each phase should keep the full suite green and include targeted tests.

Minimum tests:

- `tests/test_memory_lint.py`
- `tests/test_memory_lint_helpers.py`
- `tests/test_encoding_gate_cleanup.py`
- `tests/test_hooks_encoding_gate.py`
- release-gate quick path:

```bash
node cli/index.js release-gate --quick --no-semantic
```

For helper integration specifically:

- Assert `MemoryLint.extract_links()` returns the same type and values as before.
- Assert `MemoryLint._extract_frontmatter()` returns the same dict shape as before.
- Assert helper functions are imported by at least one production-side module.
- Assert no preparatory/unused warning remains once helpers are wired.

## Acceptance criteria mapping for Issue #11

Issue #11 criteria and planned satisfaction:

- `scripts/memory_lint_helpers.py` no longer carries preparatory/unused warning:
  - complete after Phase 2.
- At least one production-side module imports public symbols from `memory_lint_helpers.py`:
  - already true for `EncodingGate`; broaden in Phase 2 for `FrontmatterExtractor`, `SafeFileOperations`, and/or `ValidationHelpers`.
- `MemoryLinter` no longer holds duplicated helper logic:
  - addressed incrementally in Phases 2-5.
- Tests cover helpers in their new home:
  - existing EncodingGate tests remain; add helper integration tests in Phase 2.
- No regression in pytest, ruff, pylint, mypy, bandit:
  - required for each PR.

## Review constraints

Keep PRs small:

1. Design doc only.
2. Helper integration, no module movement.
3. Encoding command split.
4. Layer 1 split.
5. Layer 2/checklist split.

Avoid combining architectural movement with behavior changes.

## Recommended next PR

Implement Phase 2:

- import `FrontmatterExtractor`, `SafeFileOperations`, and optionally `ValidationHelpers` in production code
- preserve the `MemoryLint` public methods used by tests
- update `memory_lint_helpers.py` docstring from `PARTIALLY INTEGRATED` to production helper module wording
- add regression tests proving production imports and equivalent parsing behavior
