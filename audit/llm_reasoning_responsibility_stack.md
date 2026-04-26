# Audit #2 — LLM-reasoning Responsibility Stack

**Date:** 2026-04-25
**Scope:** the `mergelord/claude-4layer-memory` repository as of `main` after PR #10 (`ce8bfac`).
**Question:** for each user-facing workflow in this system, what currently lives in the *deterministic* layers (state / triggers / scripts / skills / policy) versus the *LLM reasoning* layer? Where has LLM reasoning crept up the stack into a place where a more deterministic component would be more reliable?

The framing follows the "responsibility stack" model:

```
    ┌──────────────────────────────┐
 6. │ LLM reasoning                │   synthesis · ambiguity · trade-offs
    ├──────────────────────────────┤
 5. │ Policy / docs                │   what we promise · constraints
    ├──────────────────────────────┤
 4. │ Skills / runbooks / procedures│   reusable how-to
    ├──────────────────────────────┤
 3. │ Scripts / tools / automations│   deterministic execution
    ├──────────────────────────────┤
 2. │ Triggers / hooks             │   what wakes the system up
    ├──────────────────────────────┤
 1. │ State                         │   files · DBs · indexes
    └──────────────────────────────┘
```

The healthy default is: **as much weight as possible in 1–4, with 6 reserved for synthesis the user actually wants.** Repeated, threshold-based, or critical work that lives in 6 is a smell.

---

## 1. Workflow-by-workflow audit

### 1.1 Auto-context loading on `UserPromptSubmit`

**Description.** When the user submits a prompt to Claude Code, the `semantic_search.py` hook decides whether to enrich the prompt with results from the global memory.

**Current placement of responsibility:**

| Layer | What lives here | OK? |
| --- | --- | --- |
| 1. State | `semantic_db_global/`, `memory_fts5.db`, `memory/*.md` | ✅ |
| 2. Triggers | `UserPromptSubmit` Claude Code hook | ✅ |
| 3. Scripts | `semantic_search.py` decides whether to query, `l4_semantic_global.py` runs it | ✅ |
| 4. Skills | Hook documentation in `MEMORY_SYSTEM_GUIDE.md` | ✅ |
| 5. Policy | `MANDATORY_CONTEXT_CHECK.md` instructs the agent to acknowledge results | ✅ |
| 6. LLM | Synthesizes the retrieved snippets into a coherent answer | ✅ |

**Verdict.** Healthy. The decision *whether to query* is in scripts (deterministic substring match on `TRIGGERS`); the actual ranking is in indexes; the LLM only synthesizes the result.

**Latent issue.** `TRIGGERS` is a hand-curated list inside `scripts/semantic_search.py:39`. As the language and product expand, this list will drift. A user adding a new trigger today edits production source.

**Recommendation.** Move `TRIGGERS` into `config/triggers.yml` (or similar), keep the substring logic, and let the deploy-script re-export it. This shrinks the "edit Python to change behaviour" surface. Low priority.

### 1.2 Layer 1 — pre-delivery checklist (`memory_lint.py --pre-delivery`)

**Description.** Before the user delivers a session summary, `memory_lint` runs seven structural checks (frontmatter, broken links, oversize files, etc.).

**Current placement:**

| Layer | What lives here | OK? |
| --- | --- | --- |
| 1. State | `memory/*.md` | ✅ |
| 2. Triggers | CLI subcommand or pre-commit hook | ✅ |
| 3. Scripts | `memory_lint.py`, `memory_lint_helpers.py`, registries in `consistency_checkers.py` and `antipattern_checkers.py` | ✅ |
| 4. Skills | `memory_lint_full.bat`, `memory_lint_quick.bat` | ✅ |
| 5. Policy | `MEMORY_LINT_REFACTORING_REPORT.md` documents what each check is for | ✅ |
| 6. LLM | Not involved | ✅ |

**Verdict.** Healthy. This is the gold-standard example of "fully in deterministic layers". PR #10 strengthened the registries with `try/except` wrappers per checker (one bad check no longer crashes the sweep) and added `TypedDict` result schemas.

### 1.3 Layer 2 — semantic checks (`memory_lint.py --layer 2`)

**Description.** Higher-level checks: "are there contradictions across files", "is anything claimed here outdated", "are similar terms used inconsistently".

**Current placement:**

| Layer | What lives here | OK? |
| --- | --- | --- |
| 1. State | `memory/*.md` | ✅ |
| 2. Triggers | CLI subcommand | ✅ |
| 3. Scripts | `_build_contradiction_prompt`, `_build_outdated_prompt`, registries | ✅ formatting |
| 6. LLM | Decides what counts as a contradiction / outdated claim | ⚠️ |

**Verdict.** Mixed — and that is on purpose. *Genuine* contradiction detection between free-text statements is exactly the LLM's job; a regex can't tell that "we deploy on Mondays" contradicts "deploys are blocked on weekdays". But a number of *deterministic* sub-checks have been creeping into this layer over time:

- terminology drift ("memory" vs "Memory" vs "MEMORY")
- duplicate rule statements (verbatim and near-verbatim)
- cross-file URL / path inconsistency
- "claim mentions a date that has passed without being updated"

PR #7 already promoted the first three into `consistency_checkers.py` / `antipattern_checkers.py`, which is the right move. The fourth is still implicit in the LLM prompt for "outdated claims".

**Recommendation.** Add an `OutdatedDateChecker` in `consistency_checkers.py` that:

1. Parses a date from any statement matching `(updated|valid until|expires?) on YYYY-MM-DD`.
2. Compares to `datetime.now()`.
3. Emits a `consistency` warning if the date is in the past.

This drains a class of checks out of the LLM prompt and into a regex/date arithmetic check, leaving the LLM to deal with genuinely ambiguous "is this still true?" cases.

### 1.4 Skill creator pattern detection (`skill_creator.py`)

**Description.** Walks `~/.claude/projects/*.jsonl` session logs, looks for repeated user-prompt patterns + their success rate, and proposes new SKILL files when both thresholds are met.

**Current placement:**

| Layer | What lives here | OK? |
| --- | --- | --- |
| 1. State | session JSONLs | ✅ |
| 3. Scripts | counts patterns, computes success rate, applies thresholds | ✅ |
| 5. Policy | "min 3 occurrences, ≥80% success rate" | ✅ (parametrized in PR #10) |
| 6. LLM | Synthesizes the SKILL file body from the patterns | ✅ |

**Verdict.** Healthy after PR #10. Thresholds were hardcoded constants; PR #10 lifted them to `__init__` parameters with sensible defaults (`DEFAULT_MIN_PATTERN_COUNT=3`, `DEFAULT_MIN_SUCCESS_RATE=0.8`). The clustering (which prompts go together) is deterministic. The narrative ("here is a skill that...") is LLM, which is correct.

### 1.5 Cost tracking — observability *without* a gate

**Description.** `cost_tracker.py` writes to a SQLite DB every time a search hook fires. There is a `get_stats()` method (which PR #10 fixed for the local-time TZ bug) that reports total cost.

**Current placement:**

| Layer | What lives here | OK? |
| --- | --- | --- |
| 1. State | `memory_costs.db` | ✅ |
| 3. Scripts | `add_usage`, `get_stats` | ✅ |
| 5. Policy | `feedback_token_budget_warnings.md`: "warn at 75% / 90% of budget" | ⚠️ |
| 6. LLM | Reads stats, decides whether to warn the user | ⚠️ |

**Verdict.** This is the **single biggest example** of LLM-reasoning leak in the repo. The policy says "warn the user when they cross 75% / 90% of budget", but there is no deterministic gate that *enforces* it. The agent is supposed to look at `get_stats()` and remember to warn. Sometimes it does, sometimes it forgets — exactly the behaviour the responsibility-stack model predicts.

**Recommendation (concrete).** Add a `CostBudgetGate` to `cost_tracker.py`:

```python
class CostBudgetGate:
    def __init__(
        self,
        warn_at_fraction: float = 0.75,
        block_at_fraction: float = 1.0,
        budget_per_day_usd: float | None = None,
    ): ...

    def check(self) -> "BudgetVerdict":
        """Returns one of: OK, WARN_75, WARN_90, BLOCKED."""
        ...
```

Have `semantic_search.py` call `gate.check()` *before* invoking `l4_semantic_global.py`. The gate emits a deterministic stderr line when it crosses 75 % (`[budget] warn 75 %`) and a deterministic exit code when it would cross the daily budget. The LLM still composes the user-facing wording, but the *trigger* to warn moves from "LLM remembers to" → "deterministic gate fires".

This is the pattern: **state in layer 1 → gate in layer 3 → LLM phrasing in layer 6.** Today the gate is missing.

### 1.6 Hot-memory rotation (`hooks/rotate_hot_memory.py`, `rotate_to_cold.py`)

**Description.** Time-based rotation of `handoff.md` entries into `decisions.md` after 24 hours.

**Current placement:**

| Layer | What lives here | OK? |
| --- | --- | --- |
| 1. State | timestamp on each handoff entry | ✅ |
| 2. Triggers | `SessionStart` hook + scheduled task | ✅ |
| 3. Scripts | `rotate_to_cold.py` | ✅ |
| 5. Policy | `ROTATION_SETUP.md` documents "24h rotation" | ✅ |
| 6. LLM | Not involved | ✅ |

**Verdict.** Healthy. Pure deterministic rotation.

### 1.7 Crash recovery (`hooks/crash-recovery.py`)

**Description.** If the previous session ended unexpectedly, load the partially saved state and synthesize a "where we left off" summary.

**Current placement:**

| Layer | What lives here | OK? |
| --- | --- | --- |
| 1. State | crash marker file | ✅ |
| 2. Triggers | `SessionStart` | ✅ |
| 3. Scripts | parse marker, format prompt | ✅ |
| 6. LLM | Synthesizes recovery summary | ✅ |

**Verdict.** Healthy. The decision *whether to recover* is deterministic (marker exists or not); only the narrative is LLM.

### 1.8 Encoding integrity of hot memory writes

**Description.** Hooks like `auto-remember.py` and `autosave-context.py` append to `memory/handoff.md` with text gathered from sub-shells and `git log` output.

**Current placement:**

| Layer | What lives here | OK? |
| --- | --- | --- |
| 1. State | `handoff.md` (UTF-8 markdown) | ⚠️ — corrupted in some installations |
| 3. Scripts | hooks that write the file | ⚠️ — encoding not enforced |
| 6. LLM | Reads the file at session start | downstream victim |

**Verdict.** This is a **silent failure mode that surfaces as "the agent forgets things"**. We saw it concretely in the user-supplied snapshot:

```
**Сообщение:** Р РµС„Р°РєС‚РѕСЂРёРЅРі 6 РјРѕРґСѓР»РµР№: ...
```

That string is `cp1251` bytes interpreted as `utf-8`. The hook collected output from a sub-shell that printed in `cp1251` and wrote it to a `utf-8` file without re-encoding, so the next session's LLM cannot understand its own hot memory.

The system has **no gate** that fails such a write. The LLM is left to either work around the garbled text (and blame "the model" for forgetting) or pretend it understood it.

**Recommendation.** Add an `EncodingGate` in `memory_lint_helpers.py` (this is a good first consumer for the helpers module that PR #10 deferred — see issue #11):

```python
def assert_utf8_clean(path: Path) -> None:
    """Refuse to commit a memory file with invalid UTF-8 or replacement chars.

    Detect mojibake by looking for the '\ufffd' replacement char OR for
    cp1251-as-utf8 byte patterns (sequences of two bytes both in 0xc0..0xdf
    that decode to Cyrillic-block U+0420..U+044f). Raise EncodingError so the
    write hook fails loudly instead of corrupting the file silently.
    """
```

Wire this into `auto-remember.py`, `autosave-context.py`, `precompact-flush-l4.py` before they write. Add a `--validate-encoding` switch to `memory_lint.py --layer 1` so existing files are flagged.

### 1.9 Hook router itself (`settings.json` → which hook fires when)

**Description.** Claude Code's own hook config decides routing. Our system contributes scripts; the routing lives in the user's `~/.claude/settings.json`.

**Current placement:**

| Layer | What lives here | OK? |
| --- | --- | --- |
| 2. Triggers | `settings.json` event names (`SessionStart`, `PreCompact`, `UserPromptSubmit`, `Stop`) | ✅ |
| 3. Scripts | hook scripts | ✅ |
| 6. LLM | Not involved in routing | ✅ |

**Verdict.** Healthy. Routing is fully declarative.

**Latent issue.** A user can have stale entries in `settings.json` pointing at hooks that no longer exist (or that have been moved between `hooks/` and `scripts/` — the user's snapshot has both, with diverged content). Today nothing detects that.

**Recommendation.** Add a `claude-memory-cli verify-hooks` subcommand that:

1. Parses `~/.claude/settings.json`.
2. Resolves each `command` to a path.
3. Asserts the file exists, is readable, and was last modified within the same major version as the rest of the install.

This is consumed by the deploy-script we ship next.

## 2. Cross-cutting issues

### 2.1 Repeated logic that today only lives in the LLM

| Repeated decision | Where it should live | Where it lives today |
| --- | --- | --- |
| "Is the cost-budget warning threshold crossed?" | `cost_tracker.CostBudgetGate.check()` (layer 3) | LLM remembers to glance at `get_stats()` (layer 6) |
| "Is this handoff.md text clean UTF-8?" | `memory_lint_helpers.assert_utf8_clean()` (layer 3) | LLM tries to read it and reports failure as "I don't remember" (layer 6) |
| "Should the auto-search hook run for this prompt?" | `semantic_search.TRIGGERS` (layer 3) | already deterministic ✅ |
| "Has this date passed without being updated?" | `consistency_checkers.OutdatedDateChecker` (layer 3) | mixed in with LLM `outdated_claims` prompt (layer 6) |
| "Does this hook still exist on disk?" | `claude-memory-cli verify-hooks` (layer 3) | nobody — discovered when the hook silently fails (layer 6) |

### 2.2 What is correctly in the LLM and should stay there

- Final answer synthesis after the auto-search hook returns snippets.
- Genuine contradiction detection (between free-text statements that don't share keywords).
- Skill description prose given a cluster of session prompts.
- Handoff.md narrative composition at session end.
- Recovery-summary synthesis after a crash.

## 3. Concrete next-step backlog

Ranked by *impact on user-visible reliability* divided by *implementation cost*:

| Priority | Item | Effort | Link |
| --- | --- | --- | --- |
| 1 | `EncodingGate` for `handoff.md` writes (fixes "agent forgets") | S | §1.8 |
| 2 | `CostBudgetGate.check()` + 75 %/90 % deterministic warnings | S | §1.5 |
| 3 | `OutdatedDateChecker` in `consistency_checkers.py` | S | §1.3 |
| 4 | `claude-memory-cli verify-hooks` subcommand | S | §1.9 |
| 5 | `tests/test_independence_invariant.py` (lock the property from Audit #1) | XS | Audit #1 §5 |
| 6 | Move `TRIGGERS` to `config/triggers.yml` | S | §1.1 |
| 7 | `claude-memory-cli prefetch` for offline first-run | M | Audit #1 §4.1 |

Items 1–4 each move *exactly one* repeated/critical decision out of layer 6 into a deterministic layer. Item 5 keeps the audit-1 invariant from regressing. Items 6–7 are polish.

These will be tracked as separate GitHub issues / mini-PRs after this audit document lands.
