# MemoryLinter Split Design

## Status

**Deferred. Do not implement speculatively.**

This document is a backlog design note for Issue #11: `Integrate memory_lint_helpers.py during MemoryLinter split`.

The design below is intentionally **not** an approved immediate migration plan. The current production position is:

- If CI is green, the functionality is not broken, and the implementation fully satisfies current customer production needs, then a structural refactor is premature.
- A split should happen only after real production usage shows concrete maintenance pain, a confirmed bug, a security/operational blocker, or a customer need that cannot be safely satisfied in the current structure.
- Until then, keep `memory_lint.py` stable and avoid introducing new modules solely to satisfy theoretical architecture concerns.

This document does not change the public `memory_lint.py` CLI surface and does not require any runtime changes.

## Production decision

The proposed multi-module split is explicitly deferred because its ownership cost is non-trivial:

- more modules to document and keep synchronized;
- more import boundaries and integration points;
- more test surfaces for every behavior change;
- more risk of circular imports or CLI compatibility regressions;
- more onboarding complexity for future maintainers.

Those costs are not justified while the current code is passing CI, satisfying the production baseline, and has no confirmed runtime failure.

## When to revisit

Revisit this design only if at least one of these triggers appears:

- `memory_lint.py` has a confirmed production bug that is hard to fix safely in the current structure;
- the current structure blocks a customer-requested feature;
- repeated changes to Layer 1 / Layer 2 / encoding logic become risky or error-prone;
- reviewer feedback blocks a release because of the current structure;
- a security or correctness issue requires isolating part of the implementation;
- production usage shows real maintenance pain rather than theoretical complexity.

Absent one of these signals, prefer stability over refactoring.

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

Today, `EncodingGate` is production code and is already imported by `memory_lint.py`. The other helpers are mostly preparatory. That is acceptable while there is no production pressure to split the linter.

## Current default approach

Keep the current structure:

- `scripts/memory_lint.py` remains the stable CLI and orchestration implementation.
- `scripts/memory_lint_helpers.py` remains available helper infrastructure.
- Do not create new `memory_lint_*` modules without a concrete production trigger.
- Do not refactor only to remove theoretical duplication.
- Prefer targeted bug fixes and regression tests over broad structural changes.

## Non-goals while deferred

- No immediate split into new modules.
- No immediate helper integration PR.
- No CLI surface changes.
- No behavior changes to `--layer`, `--quick`, `--checklist`, `--report`, `--validate-encoding`, `--repair-mojibake`, or `--apply`.
- No attempt to close Issue #11 merely for architectural cleanliness.

## Possible future module shape

If a real trigger appears, the following shape can be reconsidered. This is **not** current work.

### `scripts/memory_lint.py`

Would remain the CLI entrypoint.

Possible responsibilities after a future split:

- parse CLI args
- resolve memory path
- dispatch to encoding operations, checklist, or lint layers
- translate result objects into process exit codes

### `scripts/memory_lint_core.py`

Could own the `MemoryLint` orchestration class.

Possible responsibilities:

- load config
- coordinate Layer 1 and Layer 2 checks
- own lifecycle-level methods such as `run_layer1`, `run_layer2`, `generate_report`, and `clear_cache`
- depend on smaller checker/helper modules

### `scripts/memory_lint_layer1.py`

Could own deterministic checks:

- ghost links
- orphan files
- duplicate titles
- HOT age
- WARM age
- file sizes
- project publication status

### `scripts/memory_lint_layer2.py`

Could own semantic and heuristic checks:

- contradiction prompt construction
- outdated claims
- consistency registry integration
- completeness markers
- anti-pattern registry integration

### `scripts/memory_lint_checklist.py`

Could own pre-delivery checklist composition:

- no duplicate memories
- all links valid
- frontmatter complete
- HOT memory fresh
- WARM memory fresh
- file sizes OK
- Why/How sections present

### `scripts/memory_lint_encoding.py`

Could be a thin wrapper around encoding CLI operations:

- `_safe_rglob_md`
- validate encoding command
- repair mojibake command
- repair summary printing

This module would continue to import `EncodingGate` from `memory_lint_helpers.py`.

## Future migration plan, if justified

Only use this plan after a revisit trigger is met.

### Phase 1 — evidence and scope

- Identify the concrete bug, blocker, or production maintenance pain.
- Define the smallest refactor needed to address that specific problem.
- Keep the public CLI contract unchanged unless a customer requirement says otherwise.

### Phase 2 — helper integration without moving checks

If needed, start with the smallest low-risk change:

- Keep method names on `MemoryLint` for compatibility with existing tests.
- Delegate parsing helpers where it reduces duplicated logic without changing behavior.
- Add regression tests proving equivalent behavior.

### Phase 3 — split only the painful area

If helper integration is not enough, extract only the component causing real pain. For example:

- encoding CLI operations if encoding maintenance becomes risky;
- Layer 1 deterministic checks if those checks require active development;
- checklist orchestration if checklist behavior starts changing frequently.

Avoid extracting all layers at once.

## Test strategy for any future refactor

Every future runtime refactor must keep the full suite green and include targeted tests.

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
- Assert any newly production-imported helper has direct regression coverage.

## Issue #11 position

Issue #11 remains valid as backlog, but should not drive speculative runtime changes.

Acceptance criteria should be pursued only when the project has a concrete reason to touch `memory_lint.py`:

- confirmed production bug;
- customer-requested feature;
- release-blocking reviewer feedback;
- security/correctness issue;
- repeated maintenance pain.

Until then, leave the current implementation stable.

## Recommended next production work

Do not implement the split now.

Prefer production-facing, low-risk work:

- polish GitHub Release notes for `v1.6.2`;
- validate the real working installation, not only a clean clone;
- verify README / INSTALL / BOOTSTRAP against actual setup steps;
- update the GitHub repository description manually;
- collect production evidence before revisiting architecture.
