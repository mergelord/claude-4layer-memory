# Migration notes — `install_to_claude_dir.ps1`

This document is the diff between **what the deploy script touches**
and **what it leaves alone**. Read it before your first run.

If you came here looking for the user-facing install steps, see
[`INSTALL_WINDOWS.md`](./INSTALL_WINDOWS.md). This file is the
implementation contract — what's safe, what's at risk, and what
recovery looks like.

## What the script does, in order

1. **Validate source repo**: refuses to run unless the source
   directory contains `VERSION` and `scripts/memory_lint_helpers.py`.
2. **Validate target Claude dir**: refuses to run unless the target
   directory contains `CLAUDE.md`.
3. **Check for running Claude processes** (`Claude`, `claude`,
   `claude-code`). Aborts unless `-Force` is passed.
4. **Backup the entire target tree** to
   `<BackupRoot>\.claude.backup-YYYYMMDD-HHMMSS\` via
   `robocopy /MIR`. (Skipped if `-SkipBackup`.)
5. **Resolve stale package-shadowing directories.** For each
   managed directory, scan the repo source for `*.py` files; if the
   target contains a directory of the same stem (e.g. `scripts\
   memory_lint\` shadowing the v1.3.0 `scripts\memory_lint.py`),
   rename it aside to `<stem>.stale-YYYYMMDD-HHMMSS\`. Without this
   step Python's import resolver picks the package over the module
   and silently breaks `EncodingGate` imports. The original is in
   the timestamped backup *and* in-place under the `.stale-*` name,
   so rolling back is just renaming back.
6. **Sync managed directories** with `robocopy /E` (recursive,
   include empty subdirs) — but **without** `/MIR`, so files unique
   to the target are not deleted.
7. **Sync managed root files** with `Copy-Item -Force`.
8. **Run validation**:
   - **Sanity:** `python -c` block that imports `EncodingGate` from
     `scripts/memory_lint_helpers.py` and reads `VERSION`. This
     exercises the full `scripts/` tree (helper modules, package
     resolution) end-to-end. We don't call `memory_lint.py --version`
     because the script has no such flag — it's an auditor, not a
     CLI tool with metadata commands.
   - `python scripts/memory_lint.py memory --validate-encoding` —
     reports any cp1251-as-utf8 mojibake under `memory\`. Non-zero
     exit is **expected** if you have legacy corruption; that's a
     signal to run `--repair-mojibake --apply` afterwards, not a
     deploy failure.
   - `python -m pytest tests/ -q --ignore=tests/test_architecture.py`
     — runs every unit test for the deployed modules but skips the
     repo-invariant architecture tests. Those tests scan the entire
     project root for `*.bak`, `*.backup`, `*.old`, `*~` files,
     which is the right policy for a development checkout but the
     wrong policy for a deployed install (where they walk your
     runtime data, e.g. `hooks\rotate_to_cold.py.backup`,
     `projects\<id>\memory\handoff.md.bak`, and almost always find
     legitimate user-created files).
9. **Print a summary** with the backup path and rollback command.

## Managed paths (synced FROM repo INTO `.claude\`)

Anything in this list is **overwritten** by the deploy. If you
hand-edit any of these paths, your changes are lost (the backup
contains the previous version, but you'll need to merge by hand).

### Directories

The script invokes `robocopy <Source>\<dir> <Target>\<dir> /E` for
each of:

| Path | Purpose |
|--|--|
| `scripts\` | All Python scripts (memory_lint, EncodingGate helpers, l4 search, cost_tracker, etc.). Refactored heavily in v1.3.0. |
| `cli\` | Node.js CLI commands (`cli/index.js`, `cli/commands/*`). |
| `tests\` | The pytest suite — shipped so you can re-run validation locally. |
| `utils\` | Shared utilities (`base_reporter`, `colors`). |
| `templates\` | `.template` files for HOT memory + handoff/decisions stubs. |
| `docs\` | Markdown documentation. |
| `examples\` | Example configs / sample memory snippets. |
| `audit\` | Auditing reports (`independence_from_external_ai.md`, `llm_reasoning_responsibility_stack.md`, etc.). |
| `deploy\` | This script + these notes. (Yes, the deploy script is itself part of the deploy.) |
| `config\` | Default config files. **See "Risk paths" below** — the deploy will overwrite repo-tracked config; user-specific config that doesn't have a repo counterpart is left alone. |

`/E` recurses into subdirectories and includes empty ones; the
default robocopy behaviour overwrites destination files with newer
or equal-timestamped source files. Files in the destination that
have **no repo counterpart** are kept (no `/MIR`).

### Root files

| File | Purpose |
|--|--|
| `VERSION` | Plain `1.3.0\n`. Read by `memory_lint --version` and the deploy script's sentinel check. |
| `LICENSE` | The repo's license file. |
| `README.md`, `CHANGELOG.md`, `CREDITS.md` | Top-level project docs. |
| `ARCHITECTURE_ANALYSIS.md`, `ANTIPATTERNS_FIX.md`, `CODE_QUALITY_REPORT.md`, `FINAL_SUMMARY.md`, `MCP_SERVER.md`, `PROJECT_STATUS.md`, `SECURITY_AUDIT_REPORT.md` | Audit / status reports. |
| `audit.py`, `audit.bat`, `audit.sh` | The pre-install audit tool. |
| `analyze_project.py` | Project structure analyser. |
| `architecture_analysis.bat` | Wrapper around the analyser. |
| `mcp_server.py`, `mcp_config.json` | MCP server entry point and config. |
| `package.json`, `package-lock.json` | Node.js metadata. (Note: the deploy does **not** run `npm install` for you — see "Post-deploy you may want to" below.) |
| `install.bat`, `install.sh` | Fresh-install scripts (kept for new-machine bootstraps). |

If a file in this list is missing from the source repo (e.g. you're
on an older branch), the deploy logs `(missing in repo, skipped)`
and continues.

## Paths the script never touches

The deploy script **does not** mention any of the following in its
robocopy invocations, so they survive the deploy untouched. These
are your runtime data and personal customisations.

| Path | Why preserved |
|--|--|
| `memory\` | Your actual memory tree. The whole point of the system. |
| `sessions\` | Claude Code session state. |
| `projects\` | Per-project data Claude Code maintains. |
| `file-history\` | Claude Code's file edit history. |
| `cache\`, `paste-cache\`, `shell-snapshots\` | Local caches; rebuilt on demand. |
| `semantic_db_global\` | ChromaDB persistent store for semantic search. Rebuilding from scratch is expensive — losing it would invalidate hours of indexing. |
| `session-env\`, `ide\`, `feedback\`, `plans\`, `tasks\`, `telemetry\`, `plugins\` | Various Claude Code runtime state. |
| `backups\` | Your historical backup directory (separate from the deploy's own backup). |
| `hooks\` | **All your hooks.** The repo doesn't have a `hooks/` dir, so the deploy never overwrites them. If you need to update a specific hook, pull it manually from `scripts/` (where many hooks live in the repo) and copy it to `hooks\` yourself. |
| `skills\` | Your personal skill definitions. |
| `rules\` | Your rule definitions. |
| Top-level files like `settings.json`, `.crash_recovery_processed.json`, `bandit_*.json`, `prospector_*.json`, `ruff_report.json`, `skill_patterns.json`, `upstream_check_state.json`, `hookify.session.local.md` | Runtime state files written by hooks. None are repo-tracked. |
| Top-level docs the user generated themselves (e.g. `ACTIVE_SKILLS.md`, `INSTALLATION_INFO.md`, `MEMORY_SYSTEM_GUIDE.md`, `OPTIMIZATION_APPLIED.md`, `ROTATION_SETUP.md`, `SYSTEM_ARTIFACTS.md`, `UPDATE_REPORT.md` …) | These have no repo counterpart and aren't in the managed root-files list. |

## Risk paths (worth eyeballing the dry-run for)

Three managed paths exist in **both** the repo and a typical
`.claude\` install. The deploy will overwrite the repo-tracked
contents of each. If you've made local edits, they'll be replaced.

| Path | What's in repo | What might be in your `.claude\` |
|--|--|--|
| `scripts\` | Refactored modules + new EncodingGate. | Older versions of the same files plus a few user-only scripts (e.g. `memory_lint_old.py`, custom `l4_*.bat`). The user-only files are kept; the repo-tracked ones are overwritten. |
| `config\` | Default config / schema files. | You may have edited config under here for personal preferences. Diff before running. |
| `tests\` | The repo test suite. | Probably nothing of yours, unless you've added local test fixtures. |

**If in doubt:** run `-DryRun` first, scroll through the per-path
output, and look for `Newer` or lines pointing at files you don't
recognise.

## Robocopy flags reference

Each managed-dir sync is invoked as:

```
robocopy <src> <dst> /E /R:1 /W:1 /NP /NDL /NJH /NJS [/L] [/XD ...] [/XF ...]
```

| Flag | Meaning |
|--|--|
| `/E` | Recurse into all subdirs, including empty ones. |
| `/R:1 /W:1` | Retry once with a 1-second wait on transient failures. (Robocopy's defaults are 30 retries × 30 seconds — disastrous if a file is locked.) |
| `/NP` | No per-file progress percentage — keeps the log readable. |
| `/NDL` | No directory list — only changes are printed. |
| `/NJH /NJS` | No job header / job summary — the deploy script prints its own. |
| `/L` | List-only (dry-run). Added when `-DryRun` is passed. |
| `/XD <dirs>` | Excluded directories (see below). |
| `/XF <files>` | Excluded files (see below). |

The backup step uses a **different** invocation:
`robocopy <Target> <BackupPath> /MIR /R:1 /W:1 /NP /NDL /NJH /NJS /COPY:DAT`
— `/MIR` is safe here because the destination is a fresh,
just-created directory, and `/COPY:DAT` preserves data, attributes,
and timestamps.

### Excluded directories (`/XD`)

```
.git, .github, node_modules, __pycache__,
.pytest_cache, .ruff_cache, .mypy_cache,
.tox, .venv, venv
```

These are repo-internal or build artefacts that shouldn't propagate
into a Claude install.

### Excluded files (`/XF`)

```
*.pyc, *.pyo, .coverage, .DS_Store, Thumbs.db
```

OS / Python build clutter.

### Robocopy exit codes

The deploy script raises if `$LASTEXITCODE >= 8`. Per
[Microsoft's documentation](https://learn.microsoft.com/troubleshoot/windows-server/backup-and-storage/return-codes-used-robocopy-utility):

| Code | Meaning | Script behaviour |
|--|--|--|
| 0 | No files copied. | Pass. |
| 1 | Files copied successfully. | Pass. |
| 2 | Extra files / directories detected, no copy errors. | Pass. |
| 3 | Files copied + extras detected. | Pass. |
| 4 | Mismatched files / directories detected. | Pass. |
| 5–7 | Combinations of 1–4. | Pass. |
| 8+ | Real errors (file locked, permission denied, disk full, etc.). | **Raise**. |

## Validation step in detail

The script runs three commands from inside `.claude\`:

| Command | What it checks | Effect on verdict |
|--|--|--|
| `python -c "from memory_lint_helpers import EncodingGate; print VERSION"` | `scripts\memory_lint_helpers.py` imports cleanly *and* `VERSION` is readable. Exercises the entire `scripts\` tree end-to-end (helpers + module resolution after the shadow-resolution step). | Validation **fails** if exit ≠ 0. |
| `python scripts\memory_lint.py memory --validate-encoding` | EncodingGate finds no mojibake or U+FFFD in `memory\`. | **Warns** if exit ≠ 0 but doesn't fail the deploy — legacy mojibake is *data corruption*, not a code problem. Run `--repair-mojibake --apply` afterwards to fix. |
| `python -m pytest tests\ -q --ignore=tests\test_architecture.py` | All unit tests for the deployed modules pass (~209 tests as of v1.3.0). The architecture-invariant test is skipped because it scans the entire project root for `*.bak`/`*.backup`/`*.old`/`*~` files; on a *deployed* install those are almost always legitimate user-created backups (e.g. `hooks\rotate_to_cold.py.backup`, `projects\<id>\memory\handoff.md.bak`) and flagging them as deploy failures is wrong. The full suite (including invariants) still runs in repo CI. | Validation **fails** if exit ≠ 0. |

If validation fails (exit code 2 from the script), see "Rollback"
below.

## Rollback

The deploy script prints a `robocopy <backup> <target> /MIR`
command at the end. To roll back manually at any point:

1. Close Claude Code.
2. Run the printed command (or this template, replacing the
   timestamp):

   ```powershell
   robocopy "$env:USERPROFILE\.claude.backup-YYYYMMDD-HHMMSS" `
            "$env:USERPROFILE\.claude" /MIR /R:1 /W:1
   ```

3. Reopen Claude Code; you're back to pre-deploy state.

`/MIR` makes the target an exact copy of the source, deleting any
files that were added during the deploy. This is destructive for
*anything* in `.claude\` that wasn't in the backup, including any
new memory entries written between the deploy and the rollback.
If that's a concern, do a **partial** rollback by copying just the
specific files you need from the backup.

## Post-deploy you may want to

- Run `npm install --prefix $env:USERPROFILE\.claude` if the cli/
  components need fresh node_modules. The deploy excludes
  `node_modules\` from sync, so the existing install (if any) is
  preserved; if package.json changed, you may need to re-install.
- If `EncodingGate` reports mojibake, run
  `python scripts\memory_lint.py memory --repair-mojibake --apply`.
  See `INSTALL_WINDOWS.md` "Step 4" for the full procedure.
- Clear `__pycache__` directories if validation reports stale
  imports:
  `Get-ChildItem $env:USERPROFILE\.claude -Recurse -Filter '__pycache__' | Remove-Item -Recurse -Force`.

## Idempotence

The script is fully idempotent — running it twice with the same
source and target produces the same final state (modulo a second
backup directory). Robocopy's behaviour with `/E` and no `/MIR` is
"add new, overwrite existing, leave extras", which is naturally
idempotent.

The validation step is read-only on a clean target.

The repair step (`--repair-mojibake --apply`) is **not** triggered
automatically by the deploy and is itself idempotent — running it on
already-clean data is a no-op.

## Version-specific gotchas

### Upgrading from v1.2.0 → v1.3.0

- New: `EncodingGate` runs on every memory write. If your codebase has
  hooks that were silently emitting cp1251-as-utf8 mojibake, those
  hooks will now **fail loudly** instead of corrupting your memory.
  Fix the hook (re-decode subprocess output explicitly) rather than
  bypassing the gate.
- New: `memory_lint --validate-encoding` and `--repair-mojibake`
  subcommands. Run them once after the deploy to clean up legacy
  corruption.
- Refactored: `scripts/memory_lint.py` was split into `memory_lint.py`
  + `memory_lint_helpers.py` + four checker modules. If you imported
  internal helpers from `memory_lint` directly, update your imports.
- `package.json` version is now in sync with `VERSION` (was stuck at
  `1.0.0` since v1.0.0).

### Upgrading from older versions

If you're not sure what version you're on, run
`Get-Content $env:USERPROFILE\.claude\VERSION`. If the file doesn't
exist, you're on a pre-1.0 install — back up first, **then** consider
running `install.bat` for a fresh install instead of this sync
script.
