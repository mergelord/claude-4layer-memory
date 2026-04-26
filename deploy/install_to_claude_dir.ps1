#requires -version 5.1
<#
.SYNOPSIS
    Sync the claude-4layer-memory repo into an existing %USERPROFILE%\.claude\ install.

.DESCRIPTION
    This script is the **upgrade / sync** path, not the fresh-install path
    (use install.bat for the latter). It assumes ~/.claude/ already exists
    and contains real runtime data — your memory, sessions, projects, hooks,
    skills, semantic_db_global, etc.

    The script:

      1. Validates the source repo (must contain VERSION + scripts/memory_lint_helpers.py)
         and the target ~/.claude/ (must contain CLAUDE.md or settings.json).
      2. Refuses to run if a Claude Code process is detected (unless -Force).
      3. Creates a full timestamped backup of the entire ~/.claude/ tree
         next to it (or under -BackupRoot if specified).
      4. Robocopy-syncs each "managed" path from the repo into ~/.claude/.
         Managed paths are repo-tracked (scripts/, cli/, tests/, etc. + a
         curated list of root files). Robocopy is invoked WITHOUT /MIR so
         files that exist only in ~/.claude/ (your hooks, runtime data,
         personal skills, memory) are LEFT ALONE.
      5. Runs post-deploy validation: --version sanity check,
         memory_lint --validate-encoding, and pytest (architecture
         invariant tests are skipped -- see Step 5c in the script body).
      6. Prints a summary with the backup location and rollback instructions.

.PARAMETER Source
    Path to the local clone of mergelord/claude-4layer-memory. Defaults to
    the parent directory of this script (the repo root).

.PARAMETER Target
    Path to the Claude Code data directory. Defaults to $env:USERPROFILE\.claude.

.PARAMETER BackupRoot
    Directory in which the timestamped backup folder is created. Defaults
    to the parent of $Target (so $env:USERPROFILE by default — backup ends
    up next to .claude\).

.PARAMETER DryRun
    Show what WOULD be copied without writing anything. Backup, robocopy
    /L, and validation are all simulated.

.PARAMETER SkipBackup
    Skip the backup step. STRONGLY DISCOURAGED — only use if you have
    already taken a backup yourself (e.g. via 7z, robocopy, system restore).

.PARAMETER Force
    Bypass the "Claude Code is running" check. Use only after closing
    Claude Code yourself or accepting the risk of stale file handles.

.PARAMETER SkipValidation
    Skip the post-deploy validation step (pytest + memory_lint). Useful
    on machines without a complete Python toolchain; you should run the
    validation manually afterwards.

.EXAMPLE
    # Default: sync repo at .\ into %USERPROFILE%\.claude\, backup next to it.
    .\deploy\install_to_claude_dir.ps1

.EXAMPLE
    # Dry-run with explicit paths (recommended first step).
    .\deploy\install_to_claude_dir.ps1 -Source 'D:\src\claude-4layer-memory' `
        -Target 'C:\Users\MYRIG\.claude' -DryRun

.EXAMPLE
    # Real run with a custom backup location and Claude Code already closed.
    .\deploy\install_to_claude_dir.ps1 -BackupRoot 'D:\claude-backups' -Force

.NOTES
    Tested on Windows 10/11 with PowerShell 5.1+ and PowerShell 7+.
    Requires: robocopy (built-in on Windows), Python 3.10+ on PATH for
    validation, optional Node.js for the cli/ component.
#>

[CmdletBinding()]
param(
    [string]$Source = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path,
    [string]$Target = (Join-Path $env:USERPROFILE '.claude'),
    [string]$BackupRoot = (Split-Path -Parent $Target),
    [switch]$DryRun,
    [switch]$SkipBackup,
    [switch]$Force,
    [switch]$SkipValidation
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

# ----------------------------------------------------------------------------
# Configuration: managed paths
# ----------------------------------------------------------------------------
# Directories whose contents are repo-tracked. Each one is robocopy'd from
# $Source to $Target with /E (recursive, include empty subdirs) but WITHOUT
# /MIR — files that exist only in $Target are NOT deleted. Excludes shield
# you from accidentally syncing build artefacts.
$ManagedDirs = @(
    'scripts',
    'cli',
    'tests',
    'utils',
    'templates',
    'docs',
    'examples',
    'audit',
    'deploy',
    'config'
)

# Individual files at the root that are repo-tracked. Copied with overwrite.
$ManagedRootFiles = @(
    'VERSION',
    'LICENSE',
    'README.md',
    'CHANGELOG.md',
    'CREDITS.md',
    'ARCHITECTURE_ANALYSIS.md',
    'ANTIPATTERNS_FIX.md',
    'CODE_QUALITY_REPORT.md',
    'FINAL_SUMMARY.md',
    'MCP_SERVER.md',
    'PROJECT_STATUS.md',
    'SECURITY_AUDIT_REPORT.md',
    'audit.py',
    'audit.bat',
    'audit.sh',
    'analyze_project.py',
    'architecture_analysis.bat',
    'mcp_server.py',
    'mcp_config.json',
    'package.json',
    'package-lock.json',
    'install.bat',
    'install.sh'
)

# Robocopy-side exclusions — these never make it into $Target even if a
# careless dev added them under one of the $ManagedDirs in the repo.
$ExcludeDirs = @(
    '.git',
    '.github',
    'node_modules',
    '__pycache__',
    '.pytest_cache',
    '.ruff_cache',
    '.mypy_cache',
    '.tox',
    '.venv',
    'venv'
)
$ExcludeFiles = @(
    '*.pyc',
    '*.pyo',
    '.coverage',
    '.DS_Store',
    'Thumbs.db'
)

# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------
function Write-Header {
    param([string]$Text)
    $bar = '=' * 78
    Write-Host ''
    Write-Host $bar -ForegroundColor Cyan
    Write-Host $Text -ForegroundColor Cyan
    Write-Host $bar -ForegroundColor Cyan
}

function Write-Step {
    param([string]$Text)
    Write-Host ''
    Write-Host "[*] $Text" -ForegroundColor Yellow
}

function Write-Ok {
    param([string]$Text)
    Write-Host "    [OK] $Text" -ForegroundColor Green
}

function Write-Warn {
    param([string]$Text)
    Write-Host "    [!]  $Text" -ForegroundColor DarkYellow
}

function Write-Err {
    param([string]$Text)
    Write-Host "    [ERR] $Text" -ForegroundColor Red
}

function Assert-Sentinel {
    param([string]$Path, [string[]]$Required, [string]$Label)
    if (-not (Test-Path -LiteralPath $Path)) {
        throw "$Label not found: $Path"
    }
    foreach ($rel in $Required) {
        $full = Join-Path $Path $rel
        if (-not (Test-Path -LiteralPath $full)) {
            throw "$Label is missing required file '$rel' (looked for $full)"
        }
    }
}

function Test-ClaudeRunning {
    # Both the desktop app ("Claude.exe") and the CLI ("claude" / "claude-code")
    # may hold file handles inside %USERPROFILE%\.claude\. We treat any of them
    # as "Claude is running" for safety.
    $names = @('Claude', 'claude', 'claude-code')
    foreach ($n in $names) {
        $procs = Get-Process -Name $n -ErrorAction SilentlyContinue
        if ($null -ne $procs -and $procs.Count -gt 0) {
            return $true
        }
    }
    return $false
}

function Invoke-Robocopy {
    param(
        [string]$From,
        [string]$To,
        [switch]$Simulate
    )
    # Build robocopy argument list.
    #   /E          recurse, include empty dirs
    #   /R:1 /W:1   one retry, one second wait (defaults are 30 minutes!)
    #   /NP         no per-file progress (cleaner output)
    #   /NDL        no directory list
    #   /NJH /NJS   no job header / summary (we'll print our own)
    #   /XO         skip files that are older in source than in target?
    #               NO — we want to overwrite even when timestamps match,
    #               so we use the default behavior (newer-or-same overwrites).
    #   /XD ...     excluded directories
    #   /XF ...     excluded files
    #   /L          list-only (dry-run)
    $args = @($From, $To, '/E', '/R:1', '/W:1', '/NP', '/NDL', '/NJH', '/NJS')
    if ($Simulate) { $args += '/L' }
    if ($ExcludeDirs.Count -gt 0)  { $args += '/XD'; $args += $ExcludeDirs }
    if ($ExcludeFiles.Count -gt 0) { $args += '/XF'; $args += $ExcludeFiles }

    & robocopy @args | Out-String -Stream | Where-Object { $_ -match '\S' } | ForEach-Object {
        Write-Host "        $_"
    }
    # Robocopy exit codes 0-7 are non-error; 8+ are errors.
    # See: https://learn.microsoft.com/troubleshoot/windows-server/backup-and-storage/return-codes-used-robocopy-utility
    if ($LASTEXITCODE -ge 8) {
        throw "robocopy failed with exit code $LASTEXITCODE for $From -> $To"
    }
}

# ----------------------------------------------------------------------------
# 1. Validation
# ----------------------------------------------------------------------------
Write-Header 'Claude 4-Layer Memory: sync repo -> ~/.claude/'
Write-Host "Source     : $Source"
Write-Host "Target     : $Target"
Write-Host "BackupRoot : $BackupRoot"
Write-Host "DryRun     : $DryRun"
Write-Host "SkipBackup : $SkipBackup"
Write-Host "Force      : $Force"

Write-Step 'Validating source and target'
Assert-Sentinel -Path $Source -Label 'Source repo' -Required @(
    'VERSION',
    'scripts\memory_lint_helpers.py'
)
Write-Ok "Source repo looks good ($Source)"

Assert-Sentinel -Path $Target -Label 'Target Claude dir' -Required @(
    'CLAUDE.md'
)
Write-Ok "Target dir looks like a Claude Code install ($Target)"

if (-not $Force) {
    Write-Step 'Checking for running Claude Code processes'
    if (Test-ClaudeRunning) {
        throw "Claude Code appears to be running. Close it (or pass -Force to override) before syncing."
    }
    Write-Ok 'No Claude Code processes detected'
}

# ----------------------------------------------------------------------------
# 2. Backup
# ----------------------------------------------------------------------------
$backupPath = $null
if (-not $SkipBackup) {
    Write-Step 'Creating full backup of target'
    if (-not (Test-Path -LiteralPath $BackupRoot)) {
        if ($DryRun) {
            Write-Warn "[dry-run] Would create backup root: $BackupRoot"
        } else {
            New-Item -ItemType Directory -Path $BackupRoot -Force | Out-Null
        }
    }
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $backupPath = Join-Path $BackupRoot ".claude.backup-$stamp"
    Write-Host "    Backup destination: $backupPath"
    if ($DryRun) {
        Write-Warn "[dry-run] Would robocopy '$Target' to '$backupPath' (full mirror)"
    } else {
        # Backup uses /MIR (mirror) since the destination is a fresh dir
        # we just created. /COPY:DAT preserves data + attributes + timestamps.
        & robocopy $Target $backupPath /MIR /R:1 /W:1 /NP /NDL /NJH /NJS /COPY:DAT |
            Out-String -Stream | Where-Object { $_ -match '\S' } | ForEach-Object {
                Write-Host "        $_"
            }
        if ($LASTEXITCODE -ge 8) {
            throw "Backup robocopy failed with exit code $LASTEXITCODE"
        }
        Write-Ok "Backup created at $backupPath"
    }
} else {
    Write-Warn 'Skipping backup (-SkipBackup specified). You are responsible for rollback.'
}

# ----------------------------------------------------------------------------
# 3a. Resolve stale-package-vs-module shadowing
# ----------------------------------------------------------------------------
# Older installs can have, e.g., ``scripts\memory_lint\`` (a package
# directory from a previous refactor) AND ``scripts\memory_lint.py``
# (the current module file). When Python resolves ``import
# memory_lint`` it prefers the package directory, which silently
# shadows the v1.3.0+ module and breaks ``EncodingGate`` imports.
# Detect any ``<dir>\<stem>\`` in the target whose ``<stem>.py``
# exists in the repo source, and rename it aside (``<stem>.stale-<ts>``)
# before the sync overwrites the .py file. The original is preserved
# both in the timestamped backup AND in-place under the .stale name,
# so nothing is destroyed.
Write-Step 'Resolving stale package-shadowing directories'
$shadowsResolved = 0
foreach ($d in $ManagedDirs) {
    $sourceDir = Join-Path $Source $d
    $targetDir = Join-Path $Target $d
    if (-not (Test-Path -LiteralPath $sourceDir -PathType Container)) { continue }
    if (-not (Test-Path -LiteralPath $targetDir -PathType Container)) { continue }
    $pyFiles = Get-ChildItem -LiteralPath $sourceDir -Filter '*.py' -File `
        -ErrorAction SilentlyContinue
    foreach ($py in $pyFiles) {
        $stem = [System.IO.Path]::GetFileNameWithoutExtension($py.Name)
        $shadowDir = Join-Path $targetDir $stem
        if (Test-Path -LiteralPath $shadowDir -PathType Container) {
            $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
            $asideName = "$stem.stale-$stamp"
            $asidePath = Join-Path $targetDir $asideName
            Write-Warn "Shadow conflict: '$d\$stem\' would shadow '$d\$($py.Name)'."
            Write-Host  "        Renaming '$shadowDir' -> '$asidePath'"
            if (-not $DryRun) {
                Rename-Item -LiteralPath $shadowDir -NewName $asideName -Force
            }
            $shadowsResolved++
        }
    }
}
if ($shadowsResolved -eq 0) {
    Write-Ok 'No shadow conflicts found'
} else {
    Write-Ok "Resolved $shadowsResolved shadow conflict(s) (originals in backup + .stale-*)"
}

# ----------------------------------------------------------------------------
# 3b. Sync managed dirs
# ----------------------------------------------------------------------------
# ----------------------------------------------------------------------------
Write-Step 'Syncing managed directories from repo'
foreach ($d in $ManagedDirs) {
    $from = Join-Path $Source $d
    $to   = Join-Path $Target $d
    if (-not (Test-Path -LiteralPath $from)) {
        Write-Warn "Repo has no '$d' directory, skipping"
        continue
    }
    Write-Host "    -> $d"
    Invoke-Robocopy -From $from -To $to -Simulate:$DryRun
}
Write-Ok 'Managed directories synced'

# ----------------------------------------------------------------------------
# 4. Sync managed root files
# ----------------------------------------------------------------------------
Write-Step 'Syncing managed root files from repo'
$copied = 0
$missing = 0
foreach ($f in $ManagedRootFiles) {
    $from = Join-Path $Source $f
    $to   = Join-Path $Target $f
    if (-not (Test-Path -LiteralPath $from)) {
        $missing++
        continue
    }
    if ($DryRun) {
        Write-Host "        [dry-run] $f"
    } else {
        Copy-Item -LiteralPath $from -Destination $to -Force
    }
    $copied++
}
Write-Ok "Root files: $copied copied, $missing not present in repo (skipped)"

# ----------------------------------------------------------------------------
# 5. Post-deploy validation
# ----------------------------------------------------------------------------
$validationFailed = $false
if ($SkipValidation -or $DryRun) {
    Write-Step 'Skipping validation'
    if ($DryRun) {
        Write-Warn '(dry-run: validation always skipped on dry-run)'
    } else {
        Write-Warn '(-SkipValidation specified; run validation manually)'
    }
} else {
    Write-Step 'Validating deployed copy'

    # 5a. Sanity: VERSION readable + EncodingGate importable.
    # ``memory_lint.py`` itself has no ``--version`` flag (it's an
    # auditor, not a CLI tool with metadata commands). The equivalent
    # end-to-end check is to import the v1.3.0+ EncodingGate helper
    # while echoing VERSION; that exercises the full ``scripts\``
    # tree (helpers + module resolution) and surfaces any leftover
    # shadowing or partial-write issues.
    Push-Location $Target
    try {
        Write-Host '    -> python -c (import EncodingGate + read VERSION)'
        $sanityCmd = @"
import sys
sys.path.insert(0, 'scripts')
from pathlib import Path
from memory_lint_helpers import EncodingGate  # noqa: F401
v = Path('VERSION').read_text().strip()
print(f'OK: claude-4layer-memory {v}, EncodingGate ready')
"@
        $verOutput = & python '-c' $sanityCmd 2>&1
        if ($LASTEXITCODE -ne 0) {
            Write-Err "Sanity import / VERSION read exited $LASTEXITCODE"
            Write-Host ($verOutput | Out-String)
            $validationFailed = $true
        } else {
            Write-Ok ($verOutput | Out-String).Trim()
        }

        # 5b. EncodingGate audit on the user's actual memory tree.
        if (Test-Path -LiteralPath (Join-Path $Target 'memory')) {
            Write-Host '    -> python scripts/memory_lint.py memory --validate-encoding'
            $encOutput = & python 'scripts/memory_lint.py' 'memory' '--validate-encoding' 2>&1
            $encExit = $LASTEXITCODE
            Write-Host ($encOutput | Out-String)
            if ($encExit -ne 0) {
                Write-Warn "Encoding validation found mojibake (exit=$encExit). Run:"
                Write-Warn '    python scripts/memory_lint.py memory --repair-mojibake --apply'
                # Not flagged as $validationFailed because the user may
                # legitimately have legacy mojibake; the repair tool fixes it.
            } else {
                Write-Ok 'Encoding validation clean'
            }
        } else {
            Write-Warn 'No memory/ subdir under target; skipping encoding audit'
        }

        # 5c. Run the test suite (minus repo-invariant tests).
        # ``tests/test_architecture.py`` is a repo-invariant test
        # that scans for backup files (``*.bak``, ``*.backup``,
        # ``*.old``, ``*~``) anywhere under the project root. On a
        # development checkout that's correct -- no backups should
        # ever be checked in. On a *deployed* install it walks the
        # user's runtime data (``hooks\``, ``projects\<id>\memory\``,
        # ``sessions\``) and almost always finds something the user
        # legitimately created (e.g. ``rotate_to_cold.py.backup``,
        # ``handoff.md.bak``). It is therefore *not* a meaningful
        # signal post-deploy and we skip it here. The user can still
        # run the full suite manually if they want.
        if (Test-Path -LiteralPath (Join-Path $Target 'tests')) {
            Write-Host '    -> python -m pytest tests/ -q --ignore=tests/test_architecture.py'
            $testOutput = & python -m pytest 'tests/' '-q' '--ignore=tests/test_architecture.py' 2>&1
            $testExit = $LASTEXITCODE
            Write-Host ($testOutput | Out-String)
            if ($testExit -ne 0) {
                Write-Err "pytest exited $testExit"
                $validationFailed = $true
            } else {
                Write-Ok 'pytest passed (architecture invariants skipped)'
            }
        } else {
            Write-Warn 'No tests/ subdir under target; skipping pytest'
        }
    } finally {
        Pop-Location
    }
}

# ----------------------------------------------------------------------------
# 6. Summary
# ----------------------------------------------------------------------------
Write-Header 'Summary'
Write-Host "Source     : $Source"
Write-Host "Target     : $Target"
if ($backupPath) {
    Write-Host "Backup     : $backupPath"
} elseif ($SkipBackup) {
    Write-Host 'Backup     : (skipped)'
} else {
    Write-Host 'Backup     : (dry-run, no backup made)'
}
Write-Host "DryRun     : $DryRun"
Write-Host "Validation : $(if ($SkipValidation -or $DryRun) {'(skipped)'} elseif ($validationFailed) {'FAILED'} else {'passed'})"

if ($validationFailed) {
    Write-Host ''
    Write-Host 'VALIDATION FAILED. Recommended next steps:' -ForegroundColor Red
    Write-Host '  1. Inspect the output above for the failing test/import.'
    Write-Host '  2. If the failure is unexpected, restore from backup:'
    if ($backupPath) {
        Write-Host "       robocopy `"$backupPath`" `"$Target`" /MIR" -ForegroundColor Yellow
    } else {
        Write-Host '       (no backup was made — only manual restore is possible)'
    }
    Write-Host '  3. Open an issue at https://github.com/mergelord/claude-4layer-memory/issues'
    exit 2
}

if ($DryRun) {
    Write-Host ''
    Write-Host 'DRY-RUN complete. Re-run without -DryRun to apply changes.' -ForegroundColor Cyan
} else {
    Write-Host ''
    Write-Host 'Sync complete.' -ForegroundColor Green
    Write-Host 'Next steps:'
    Write-Host '  1. Restart Claude Code.'
    Write-Host '  2. Verify hooks load with: python scripts\memory_lint.py memory'
    Write-Host '  3. Optional: re-run encoding audit periodically:'
    Write-Host '       python scripts\memory_lint.py memory --validate-encoding'
}
