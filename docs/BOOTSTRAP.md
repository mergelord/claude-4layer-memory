# Bootstrap Guide

This guide describes the supported install/bootstrap story for Claude 4-Layer Memory System.

The project is currently distributed as a **repository-based toolchain**:

```text
git clone -> install repo dependencies -> run audit -> run installer -> verify
```

Standalone npm or pip package installation is **not** the supported path yet. Keep the cloned repository because the CLI wrapper, Python backend, hooks, constraints, docs, and release-gate checks are designed to work together from the repo root.

---

## Bootstrap model

There are two layers:

| Layer | Purpose | Location |
| --- | --- | --- |
| Repository toolchain | CLI wrapper, release gate, audit, tests, docs, MCP/dev tooling, hybrid search, memory lint | cloned repository |
| Installed hook runtime | semantic runtime wrappers, built-in Claude Code hooks, templates, local memory directories | `~/.claude` or `<L4_HOME>` |

The installer deploys the hook runtime into Claude Code's home directory. It does **not** replace the repository toolchain.

---

## Prerequisites

Required:

- Git
- Python 3.10+
- Claude Code initialized so `~/.claude` exists
- Node.js 14+ for repository CLI commands
- Network access for first-time dependency/model download
- 500MB+ free disk space for local models and indexes

Recommended:

- a project-local virtual environment
- constrained Python installs with `constraints.txt`
- running checks from a clean working tree before tagging releases

---

## Fresh bootstrap

### 1. Clone

```bash
git clone https://github.com/mergelord/claude-4layer-memory.git
cd claude-4layer-memory
```

### 2. Optional virtual environment

Linux/macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Windows Git Bash:

```bash
python -m venv .venv
source .venv/Scripts/activate
```

### 3. Install Python dependencies reproducibly

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt -c constraints.txt
python -m pip install -r requirements-dev.txt -c constraints.txt
```

### 4. Install repository CLI dependencies

```bash
npm install
```

Use `npm install` rather than `npm ci` because this repository currently does not commit a `package-lock.json`.

### 5. Audit before deployment

Windows:

```cmd
audit.bat
```

Linux/macOS:

```bash
./audit.sh
```

### 6. Deploy the hook runtime

Windows:

```cmd
install.bat
```

Linux/macOS:

```bash
chmod +x install.sh
./install.sh
```

### 7. Verify

Repository health checks:

```bash
node cli/index.js selftest --no-semantic
node cli/index.js doctor --no-semantic
node cli/index.js release-gate --quick --no-semantic
```

Installed semantic runtime check:

Linux/macOS:

```bash
python ~/.claude/hooks/l4_semantic_global.py stats
```

Windows:

```cmd
python %USERPROFILE%\.claude\hooks\l4_semantic_global.py stats
```

If semantic dependencies and local model download are available, rerun without `--no-semantic`:

```bash
node cli/index.js selftest
node cli/index.js doctor
```

---

## First indexing pass

Edit:

```text
~/.claude/GLOBAL_PROJECTS.md
```

Add the projects you want indexed, then run:

Linux/macOS:

```bash
l4_index_all.sh
```

Windows:

```cmd
l4_index_all.bat
```

Or run directly from the repository:

```bash
python scripts/l4_semantic_global.py index-all
```

---

## Upgrade bootstrap

From the repository root:

```bash
git pull --ff-only
python -m pip install --upgrade pip
python -m pip install -r requirements.txt -c constraints.txt
python -m pip install -r requirements-dev.txt -c constraints.txt
npm install
node cli/index.js selftest --no-semantic
node cli/index.js doctor --no-semantic
```

Then rerun the installer to refresh deployed hook files:

Windows:

```cmd
install.bat
```

Linux/macOS:

```bash
./install.sh
```

Read `CHANGELOG.md` for release-specific requirements. Some releases may require:

```bash
python scripts/l4_fts5_search.py reindex
python scripts/l4_semantic_global.py index-all
```

---

## What the installer deploys

The installer copies the semantic hook runtime into Claude Code's home directory:

- `scripts/l4_semantic_global.py`
- semantic helper modules such as `chunking.py` and `ranking.py`
- `memory_lint_helpers.py` for EncodingGate support in hooks
- platform `l4_*` wrappers
- built-in hooks under `hooks/builtin/`
- memory templates

It also creates:

- `~/.claude/hooks`
- `~/.claude/memory/archive`
- `~/.claude/memory/outputs`
- template memory files when missing

The installer intentionally does **not** flatten all repository tools into `~/.claude/hooks`. These remain repository-local:

- release gate
- audit tooling
- full test suite
- MCP development tools
- hybrid FTS5/BM25/rerank search
- memory lint CLI
- CI/static quality commands

---

## Troubleshooting

### `Cannot find module 'commander'`

Run from the repository root:

```bash
npm install
```

Then retry the `node cli/index.js ...` command.

### Python dependency drift

Use constrained installs:

```bash
python -m pip install -r requirements.txt -c constraints.txt
python -m pip install -r requirements-dev.txt -c constraints.txt
```

If a constraint is incompatible with your platform, record the deviation when debugging.

### Claude Code directory missing

Run Claude Code once so it initializes:

```text
~/.claude
```

Or deliberately create the target directory if you know your layout.

### Semantic/model download issues

First semantic use can download the embedding model. Check network access or set `HF_TOKEN` if HuggingFace access is required.