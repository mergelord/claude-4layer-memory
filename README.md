# Claude 4-Layer Memory System

**Version 1.6.2**

**Enterprise-grade memory management system for Claude Code with hybrid search, automatic skill discovery, and comprehensive quality assurance.**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Version](https://img.shields.io/badge/version-1.6.2-blue.svg)](https://github.com/mergelord/claude-4layer-memory/releases)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey.svg)](https://github.com/mergelord/claude-4layer-memory)
[![CI/CD](https://img.shields.io/badge/CI%2FCD-passing-brightgreen.svg)](https://github.com/mergelord/claude-4layer-memory/actions)

---

## 🎯 Features

### Core Memory System
- **4-Layer Memory Architecture** - HOT (24h) → WARM (14d) → COLD (permanent) → SEMANTIC (indexed)
- **Dual-Level System** - Global memory (cross-project) + Project memory (project-specific)
- **Auto-Discovery** - Automatically detects and indexes projects
- **Smart Filtering** - Protects against indexing system directories (`.git`, `node_modules`, etc.)

### Advanced Search & Retrieval
- **Semantic Search** - Find information by meaning, not keywords
- **Hybrid Repository Search** - FTS5 + semantic + BM25 + RRF, with optional reranking, from a full repo clone
- **Embedding Gateway** - Caching layer for embedding operations
- **MCP Server** - Model Context Protocol surface for memory search, health checks, cost tracking, and guarded code completion

> **Repository tools require a full clone.** Hybrid search, BM25 ranking, parallel search, cross-encoder reranking, memory lint, audit tooling, and MCP development flows are available from the repository but are not part of the flat installed hook runtime.

### Reliability & Hardening
- **Health checks** - `cm doctor`, MCP `health_check`, and `cm selftest`
- **Release gate** - `cm release-gate` for repeatable production-readiness checks
- **Destructive Reindex Guard** - MCP full reindex requires explicit `confirm=True`
- **Input Guardrails** - result limits and large prompt inputs are clamped
- **Daily Budget Guard** - optional `L4_DAILY_BUDGET_USD` cap for Anthropic-backed `smart_complete`
- **Routing Privacy Controls** - optional task-text hashing and history pruning
- **Structured Logs** - JSON logs under `<L4_HOME>/logs`
- **EncodingGate** - mojibake / replacement-character detection for UTF-8 hygiene
- **Path-Traversal Protection** - hardened key handling for memory operations

### CI / Quality
- Blocking tests on Python 3.10-3.13 across Ubuntu, Windows, and macOS
- Non-blocking Ubuntu / Python 3.14 experimental job
- Pylint, MyPy, Ruff, Bandit, Radon, Shellcheck, and encoding scan

---

## 🚀 Quick Start

```bash
# Clone the repository
git clone https://github.com/mergelord/claude-4layer-memory.git
cd claude-4layer-memory

# Install Python dependencies reproducibly
python -m pip install --upgrade pip
python -m pip install -r requirements.txt -c constraints.txt
python -m pip install -r requirements-dev.txt -c constraints.txt

# Install repository CLI dependencies
npm install

# IMPORTANT: run pre-installation audit first
# Windows:
.\audit.bat

# Linux/macOS:
./audit.sh

# If audit passes, run installation
# Windows:
.\install.bat

# Linux/macOS:
./install.sh

# Verify repository health quickly
node cli/index.js selftest --no-semantic
node cli/index.js doctor --no-semantic
node cli/index.js release-gate --quick --no-semantic

# Verify installed semantic runtime
python scripts/l4_semantic_global.py stats
```

---

## 📦 Installation

> Supported install mode: full Git clone plus the repository installer. `package.json` is private; npm registry installation is not supported because runtime scripts, hooks, constraints, and repository tools are required.

### Prerequisites

- Python 3.10 or higher
- Claude Code CLI installed and initialized so `~/.claude` exists
- Node.js 14+ for the repository CLI wrapper
- 500MB+ free disk space for embedding models and local DBs

### Automatic Installation

**Windows:**
```cmd
install.bat
```

**Linux/macOS:**
```bash
chmod +x install.sh
./install.sh
```

For full details, see [docs/INSTALL.md](docs/INSTALL.md).

---

## 💡 Usage

### Installed hook runtime

```bash
# Index all projects
l4_index_all.bat  # Windows
l4_index_all.sh   # Linux/macOS

# Search across all projects
l4_search_all.bat "semantic search query"

# Search global memory only
l4_search_global.bat "coding style"

# View semantic stats
l4_stats.bat
```

### Repository-only commands

Install repository CLI dependencies once before using `node cli/index.js ...` commands:

```bash
npm install
```

Then run repository checks and tools:

```bash
# Readiness checks
node cli/index.js doctor --no-semantic
node cli/index.js selftest --no-semantic
node cli/index.js release-gate --quick --no-semantic

# Full release gate before tagging
node cli/index.js release-gate --no-semantic

# Memory lint
python scripts/memory_lint.py --layer 1

# Hybrid search
python scripts/l4_fts5_search.py hybrid "memory system"

# FTS5 maintenance
python scripts/l4_fts5_search.py reindex --incremental
```

---

## ⚙️ Configuration

Default state root:

```text
~/.claude
```

Set `L4_HOME` to relocate memory state, DBs, routing learner data, and logs.

Important environment variables:

| Variable | Default | Purpose |
| --- | --- | --- |
| `L4_HOME` | `~/.claude` | Memory state root. |
| `L4_MODEL` | `paraphrase-multilingual-MiniLM-L12-v2` | Embedding model. |
| `L4_PREWARM` | `1` | Semantic prewarm on MCP startup. |
| `L4_DAILY_BUDGET_USD` | `0` / off | Daily budget for `smart_complete`. |
| `ROUTING_STORE_TASK_TEXT` | `1` | Set `0` to hash routing task text. |
| `ROUTING_HISTORY_MAX` | `0` / off | Optional routing-history retention cap. |

See [docs/guides/CONFIGURATION.md](docs/guides/CONFIGURATION.md).

---

## 📖 Documentation

- [Installation Guide](docs/INSTALL.md)
- [Operations Runbook](docs/OPERATIONS.md)
- [Production Readiness](docs/PRODUCTION_READINESS.md)
- [MCP Server](MCP_SERVER.md)
- [Architecture Overview](docs/architecture/ARCHITECTURE.md)
- [Usage Guide](docs/guides/USAGE.md)
- [Configuration Guide](docs/guides/CONFIGURATION.md)
- [Memory Lint](docs/MEMORY_LINT.md)
- [EncodingGate](docs/ENCODING_GATE.md)
- [Troubleshooting](docs/TROUBLESHOOTING.md)

---

## ✅ Production readiness

The production release gate is documented in [docs/PRODUCTION_READINESS.md](docs/PRODUCTION_READINESS.md).

Install repository CLI dependencies once:

```bash
npm install
```

Fast local gate:

```bash
node cli/index.js release-gate --quick --no-semantic
```

Full local gate before tagging:

```bash
node cli/index.js release-gate --no-semantic
```

---

## 📄 License

MIT — see [LICENSE](LICENSE).