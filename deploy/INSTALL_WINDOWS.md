# Installing claude-4layer-memory v1.3.0+ on Windows

This guide walks you through **upgrading an existing
`%USERPROFILE%\.claude\` install** with the latest repo code. It is the
upgrade / sync path; for a brand-new install on a clean machine, use
`install.bat` from the repo root instead.

## What you're about to do

1. Take a full timestamped backup of `%USERPROFILE%\.claude\`.
2. Sync repo-tracked paths from your local clone into `.claude\` —
   **without** touching your runtime data (memory, sessions, projects,
   hooks you wrote yourself, etc.).
3. Validate the deployed copy with `memory_lint --validate-encoding`
   and `pytest`.

It is safe to run repeatedly. If something goes wrong, you can roll
back by mirroring the backup directory back over `.claude\` (the
script prints the exact command).

## Prerequisites

| Requirement | Why |
|--|--|
| Windows 10/11 | The script uses `robocopy`, which ships with Windows. |
| PowerShell 5.1+ (built-in) or PowerShell 7+ | The script targets 5.1 syntax for compatibility. |
| Python 3.10, 3.11, or 3.12 on `PATH` | Validation runs `python scripts/memory_lint.py` and `python -m pytest`. |
| At least 2× free disk space of `.claude\` size | One copy for the backup, another for any in-flight robocopy buffers. The script does **not** delete the backup automatically. |
| Local clone of `mergelord/claude-4layer-memory` at `v1.3.0` or later | The script's source. |
| Claude Code **closed** | The script refuses to run if it detects a Claude process (override with `-Force` only if you know what you're doing). |

If you don't yet have a clone:

```powershell
cd $env:USERPROFILE
git clone https://github.com/mergelord/claude-4layer-memory.git
cd claude-4layer-memory
git checkout main
git pull
```

## Step 1 — Close Claude Code

Quit the Claude Code desktop app and any running `claude` / `claude-code`
CLI processes. The deploy script aborts if any are detected.

If you're not sure, run:

```powershell
Get-Process -Name 'Claude','claude','claude-code' -ErrorAction SilentlyContinue
```

Empty output = good.

## Step 2 — Dry-run (recommended)

Before writing anything, see exactly what the script will copy:

```powershell
cd $env:USERPROFILE\claude-4layer-memory
.\deploy\install_to_claude_dir.ps1 -DryRun
```

You should see, for each managed directory (`scripts`, `cli`, `tests`,
`utils`, `templates`, `docs`, `examples`, `audit`, `deploy`, `config`):

```
[*] Syncing managed directories from repo
    -> scripts
        New File ... scripts\memory_lint_helpers.py
        Newer    ... scripts\memory_lint.py
        ...
```

Plus a list of root files (`VERSION`, `LICENSE`, `README.md`,
`CHANGELOG.md`, `audit.py`, `mcp_server.py`, etc.). Anything else in
your `.claude\` — your `memory\`, `sessions\`, `projects\`,
`semantic_db_global\`, your personal `hooks\`, `skills\`, etc. — is
**not listed** because the script doesn't touch it.

If the dry-run output looks wrong (e.g. it claims it would copy your
memory tree, or it's missing files you expected), stop and inspect
the script before continuing.

## Step 3 — Real run

Once the dry-run looks right:

```powershell
.\deploy\install_to_claude_dir.ps1
```

The script will:

1. Print the source / target / backup paths it's using.
2. Verify both directories look like what they should be (sentinel
   files: `VERSION` + `scripts\memory_lint_helpers.py` in the source;
   `CLAUDE.md` in the target).
3. Confirm no Claude processes are running.
4. Create a backup at `%USERPROFILE%\.claude.backup-YYYYMMDD-HHMMSS\`
   (full mirror of `.claude\` via `robocopy /MIR`).
5. Resolve any stale package-shadowing directories. If your install
   has, e.g., `scripts\memory_lint\` (a leftover package directory
   from an older refactor) and the repo ships `scripts\memory_lint.py`
   (a single module), Python would silently pick the directory and
   shadow the new module. The script renames any such directory aside
   to `<name>.stale-YYYYMMDD-HHMMSS\` before the sync writes the .py
   file. The original is preserved both in the timestamped backup and
   in-place under the `.stale-*` name; nothing is destroyed.
6. Robocopy each managed dir into `.claude\` (`/E` recursive,
   **without** `/MIR` — files unique to your `.claude\` are left
   alone).
7. Copy the managed root files with overwrite.
8. Run validation:
   - **Sanity:** import `EncodingGate` + read `VERSION`
     (`python -c "import sys; sys.path.insert(0, 'scripts'); from memory_lint_helpers import EncodingGate; from pathlib import Path; print(Path('VERSION').read_text().strip())"`)
   - `python scripts\memory_lint.py memory --validate-encoding`
   - `python -m pytest tests\ -q --ignore=tests\test_architecture.py`
     (architecture invariants are skipped on deployed installs because
     they walk your runtime data and flag legitimate user backups; see
     `MIGRATION_NOTES.md` for details)
9. Print a summary with the backup location and next steps.

A typical run takes under a minute on an SSD. The backup step is the
slowest part (proportional to the size of `.claude\`).

### Useful flags

| Flag | When to use it |
|--|--|
| `-DryRun` | Always run this first to see what's about to change. |
| `-Force` | Skip the "Claude Code is running" check. Only use if you've manually confirmed Claude is closed and the check is a false positive (e.g. a leftover zombie process you can't kill cleanly). |
| `-SkipBackup` | Skip the backup step. **Strongly discouraged.** Only use if you've already taken a backup yourself (e.g. via 7-Zip or `wbadmin`). |
| `-SkipValidation` | Skip post-deploy `memory_lint` + `pytest`. Useful only if your machine doesn't have the full Python toolchain and you'll validate manually elsewhere. |
| `-Source <path>` | Override the repo location (defaults to the parent dir of the script). |
| `-Target <path>` | Override the Claude dir (defaults to `$env:USERPROFILE\.claude`). |
| `-BackupRoot <path>` | Put backups somewhere other than next to `.claude\` (e.g. `D:\claude-backups\`). |

## Step 4 — If validation finds mojibake

`v1.3.0` ships with `EncodingGate`. If your existing memory files
contain corrupted UTF-8 (cp1251-as-utf8 mojibake, common after running
the older `auto-remember` hook on Windows), the validator will report
it.

The output looks like:

```
memory\handoff.md: contains cp1251-as-utf8 mojibake pair 'Р°'
memory\decisions.md: contains cp1251-as-utf8 mojibake pair 'Р\xa0'
```

This is **not** a deploy failure — your code is fine; the data was
corrupted on a previous run. The deploy script does not auto-repair
data; that's a separate explicit command.

To repair, run:

```powershell
cd $env:USERPROFILE\.claude
python scripts\memory_lint.py memory --repair-mojibake          # dry-run, prints what would change
python scripts\memory_lint.py memory --repair-mojibake --apply  # actually rewrite the files
```

The repair step is idempotent (running it twice is a no-op) and uses
the same `_MOJIBAKE_RUN_RE` regex as the validator, gated by a cp1251
round-trip verification — legitimate uppercase Russian like `СССР`,
`РОССИЯ`, `СИСТЕМА` is not touched.

After repair, re-run the validator to confirm:

```powershell
python scripts\memory_lint.py memory --validate-encoding
```

## Step 5 — Restart Claude Code

Once validation is clean:

1. Reopen Claude Code.
2. The new code (`scripts\`, `cli\`, etc.) is picked up automatically
   on the next session start.
3. Verify hooks still load by running a trivial Claude prompt — if
   `auto-remember` or any `session-start.*` hook fails, the desktop
   app surfaces it in its log.

## Rolling back

If anything looks broken after the deploy:

1. Close Claude Code.
2. Run (replacing the timestamp with the one the script printed):

   ```powershell
   robocopy "$env:USERPROFILE\.claude.backup-YYYYMMDD-HHMMSS" "$env:USERPROFILE\.claude" /MIR
   ```

   `/MIR` makes `.claude\` an exact mirror of the backup, including
   deleting any files the deploy added.

3. Reopen Claude Code; you're back to the pre-deploy state.

You can also just keep using `.claude\` and patch individual files
back from the backup if only one or two things broke — `robocopy`
also accepts file-level operations.

## Cleaning up old backups

The script never deletes backups. Over many deploys, you'll accumulate
`%USERPROFILE%\.claude.backup-YYYYMMDD-HHMMSS\` directories. Once
you've confirmed a deploy is good, delete the older ones manually:

```powershell
Get-ChildItem $env:USERPROFILE -Filter '.claude.backup-*' |
    Sort-Object Name -Descending |
    Select-Object -Skip 3 |        # keep the 3 most-recent
    Remove-Item -Recurse -Force
```

## Troubleshooting

### "Source repo is missing required file 'VERSION'"

You're pointing the script at the wrong directory, or your clone is
corrupted. Run `git status` in the source dir to confirm it's a clean
checkout of the repo.

### "Target Claude dir is missing required file 'CLAUDE.md'"

You're pointing the script at the wrong directory, or this is a fresh
machine without an existing Claude install. Use `install.bat` for a
fresh install instead.

### "Claude Code appears to be running"

Close the desktop app and any CLI sessions. If the script still
detects something, look for stray processes:

```powershell
Get-Process | Where-Object { $_.ProcessName -match 'claude' }
```

Kill them, or pass `-Force` if you know they don't hold file handles
on `.claude\`.

### Robocopy returns exit code ≥ 8

Robocopy treats 0–7 as non-errors. The script raises if it sees 8 or
higher. Most common causes:

- Antivirus locking files mid-copy → temporarily allowlist the source
  and target directories.
- Permissions issue on a path inside `.claude\` → re-run the script in
  an elevated PowerShell.
- Disk full → free up space and try again.

### Validation step fails with `ImportError`

This usually means a stale `__pycache__` survived the deploy. Clear
caches and retry validation:

```powershell
Get-ChildItem $env:USERPROFILE\.claude -Recurse -Filter '__pycache__' |
    Remove-Item -Recurse -Force
cd $env:USERPROFILE\.claude
python -c "import sys; sys.path.insert(0, 'scripts'); from memory_lint_helpers import EncodingGate; from pathlib import Path; print(Path('VERSION').read_text().strip())"
```

If that still fails, restore from backup and open an issue at
<https://github.com/mergelord/claude-4layer-memory/issues>.

### Validation says encoding is dirty even after `--repair-mojibake --apply`

Run the repair against the entire `.claude\` tree (not just `memory\`),
since some legacy hook output may have leaked into other dirs:

```powershell
python scripts\memory_lint.py . --repair-mojibake --apply
python scripts\memory_lint.py . --validate-encoding
```

If that still doesn't clear it, the corrupted file may have a
non-UTF-8 byte sequence rather than mojibake — open an issue and
attach a sanitised excerpt.

## See also

- [`MIGRATION_NOTES.md`](./MIGRATION_NOTES.md) — what specifically
  changes between your previous version and this one, plus
  version-specific gotchas.
- [`install_to_claude_dir.ps1`](./install_to_claude_dir.ps1) — the
  script itself, which has full docstrings on every parameter.
- [`README.md`](../README.md) — top-level project overview.
