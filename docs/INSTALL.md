# Installation Guide

Complete installation instructions for Claude 4-Layer Memory System.

> Supported install mode: **full Git clone + repository installer**. The project is currently distributed as a repository, not as a standalone npm or pip package. Keep the clone because repository-local Python backend files, hooks, constraints, docs, and release-gate tooling are part of the supported setup.

---

## Prerequisites

Required:

- Python **3.10 or higher**
- Git
- Claude Code CLI installed and initialized so `~/.claude` exists
- 500MB+ free disk space for local embedding models and ChromaDB state

Recommended:

- A virtual environment
- Reproducible dependency install with `constraints.txt`
- Node.js 14+ for the `cm` / `claude-memory-cli` wrapper commands from the repo

---

## Quick install

```bash
git clone https://github.com/mergelord/claude-4layer-memory.git
cd claude-4layer-memory
```

Install Python dependencies:

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt -c constraints.txt
python -m pip install -r requirements-dev.txt
```

Run the pre-install audit:

```bash
# Windows
.\audit.bat

# Linux/macOS
./audit.sh
```

Run the installer:

```bash
# Windows
.\install.bat

# Linux/macOS
chmod +x install.sh
./install.sh
```

Verify:

```bash
node cli/index.js selftest --no-semantic
node cli/index.js doctor --no-semantic
```

If semantic dependencies and local model download are available:

```bash
node cli/index.js selftest
node cli/index.js doctor
```

---

## What the installer does

The installer:

- checks Python availability
- checks that `~/.claude` exists
- installs runtime dependencies from `requirements.txt` constrained by `constraints.txt`
- creates memory directories under `~/.claude`
- copies the deployed semantic runtime files into `~/.claude/hooks`
- copies built-in hooks required by the 4-layer memory flow
- creates template memory files if they do not already exist
- runs a lightweight semantic stats check

The installed hook runtime is intentionally narrower than the full repository:

- installed runtime: semantic search wrappers and built-in hooks
- repository-only tools: hybrid FTS5/BM25/rerank pipeline, memory lint, audit tooling, MCP server, CI/dev checks

Run repository-only tools from the cloned repository root.

---

## Manual install

Use this only when the automatic installer is not suitable.

### 1. Install dependencies

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt -c constraints.txt
```

### 2. Create directories

Linux/macOS:

```bash
mkdir -p ~/.claude/hooks
mkdir -p ~/.claude/memory/archive
mkdir -p ~/.claude/memory/outputs
```

Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force $env:USERPROFILE\.claude\hooks
New-Item -ItemType Directory -Force $env:USERPROFILE\.claude\memory\archive
New-Item -ItemType Directory -Force $env:USERPROFILE\.claude\memory\outputs
```

### 3. Copy runtime files

Linux/macOS:

```bash
cp scripts/l4_semantic_global.py ~/.claude/hooks/
cp scripts/chunking.py ~/.claude/hooks/
cp scripts/ranking.py ~/.claude/hooks/
cp scripts/memory_lint_helpers.py ~/.claude/hooks/
cp scripts/linux/l4_*.sh ~/.claude/hooks/
cp hooks/git-activity-detector.py ~/.claude/hooks/
cp hooks/stop_handoff_universal.py ~/.claude/hooks/
cp hooks/builtin/*.py ~/.claude/hooks/
chmod +x ~/.claude/hooks/*.py ~/.claude/hooks/*.sh
```

Windows Command Prompt:

```cmd
copy scripts\l4_semantic_global.py %USERPROFILE%\.claude\hooks\
copy scripts\chunking.py %USERPROFILE%\.claude\hooks\
copy scripts\ranking.py %USERPROFILE%\.claude\hooks\
copy scripts\memory_lint_helpers.py %USERPROFILE%\.claude\hooks\
copy scripts\windows\l4_*.bat %USERPROFILE%\.claude\hooks\
copy hooks\git-activity-detector.py %USERPROFILE%\.claude\hooks\
copy hooks\stop_handoff_universal.py %USERPROFILE%\.claude\hooks\
copy hooks\builtin\*.py %USERPROFILE%\.claude\hooks\
```

### 4. Create templates

Linux/macOS:

```bash
cp -n templates/GLOBAL_PROJECTS.md.template ~/.claude/GLOBAL_PROJECTS.md
cp -n templates/MEMORY.md.template ~/.claude/memory/MEMORY.md
cp -n templates/handoff.md.template ~/.claude/memory/handoff.md
cp -n templates/decisions.md.template ~/.claude/memory/decisions.md
```

Windows Command Prompt:

```cmd
if not exist %USERPROFILE%\.claude\GLOBAL_PROJECTS.md copy templates\GLOBAL_PROJECTS.md.template %USERPROFILE%\.claude\GLOBAL_PROJECTS.md
if not exist %USERPROFILE%\.claude\memory\MEMORY.md copy templates\MEMORY.md.template %USERPROFILE%\.claude\memory\MEMORY.md
if not exist %USERPROFILE%\.claude\memory\handoff.md copy templates\handoff.md.template %USERPROFILE%\.claude\memory\handoff.md
if not exist %USERPROFILE%\.claude\memory\decisions.md copy templates\decisions.md.template %USERPROFILE%\.claude\memory\decisions.md
```

---

## Verification

Repository-level checks:

```bash
node cli/index.js selftest --no-semantic
node cli/index.js doctor --no-semantic
python -m pytest tests/test_smoke.py -v
```

Installed semantic runtime check:

```bash
# Linux/macOS
python ~/.claude/hooks/l4_semantic_global.py stats

# Windows
python %USERPROFILE%\.claude\hooks\l4_semantic_global.py stats
```

Full test suite from the repository root:

```bash
python -m pytest tests/ -v --tb=short
```

---

## First index

After adding projects to `~/.claude/GLOBAL_PROJECTS.md`:

```bash
# Linux/macOS
l4_index_all.sh

# Windows
l4_index_all.bat
```

Or directly from the repository:

```bash
python scripts/l4_semantic_global.py index-all
```

---

## Upgrade

```bash
git pull --ff-only
python -m pip install --upgrade pip
python -m pip install -r requirements.txt -c constraints.txt
python -m pip install -r requirements-dev.txt
node cli/index.js selftest --no-semantic
```

Read `CHANGELOG.md` for release-specific reindex requirements. If required:

```bash
python scripts/l4_fts5_search.py reindex
python scripts/l4_semantic_global.py index-all
```

---

## Troubleshooting

### Python too old

Check:

```bash
python --version
```

Install Python 3.10+ and ensure it is first on `PATH`.

### `~/.claude` does not exist

Run Claude Code once so it initializes its home directory, or create the directory deliberately if you know your target layout.

### Dependency install fails

Try:

```bash
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements.txt -c constraints.txt
```

If a pinned constraint is incompatible with your platform, install without `-c constraints.txt` and record the deviation when debugging.

### Model download fails

The default sentence-transformers model may require network access on first use. Check network connectivity or set `HF_TOKEN` for HuggingFace access.

### Self-test fails

Run:

```bash
node cli/index.js doctor --no-semantic
python scripts/health_check.py --json --no-semantic
```

Then inspect logs under:

```text
~/.claude/logs/
```

or under `<L4_HOME>/logs/` if `L4_HOME` is set.

---

## Uninstall

Remove installed hooks/scripts only:

```bash
# Linux/macOS
rm -f ~/.claude/hooks/l4_*.sh
rm -f ~/.claude/hooks/l4_semantic_global.py

# Windows Command Prompt
del %USERPROFILE%\.claude\hooks\l4_*.bat
del %USERPROFILE%\.claude\hooks\l4_semantic_global.py
```

Remove generated indexes and memory data only if you are sure you no longer need them.

Regenerable data:

- `semantic_db*`
- `*.sqlite3`
- `memory_fts5.db`

User-authored memory files under `memory/` and `projects/*/memory/` should be backed up before deletion.
