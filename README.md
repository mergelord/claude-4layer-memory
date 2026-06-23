# Claude 4-Layer Memory System

**Version 1.5.1**

**Enterprise-grade memory management system for Claude Code with hybrid search, automatic skill discovery, and comprehensive quality assurance.**

> ⚠️ **Installation: git-clone only.** This project is **not published to npm**. Install it from a git clone as shown in [Quick Start](#quick-start) — the `cm` CLI runs from the cloned repository. Installing `claude-memory-cli` / `cm` from the npm registry is **not supported**: the Python backend is intentionally excluded from any npm package, so a registry install would be non-functional.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Version](https://img.shields.io/badge/version-1.5.1-blue.svg)](https://github.com/mergelord/claude-4layer-memory/releases)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey.svg)](https://github.com/mergelord/claude-4layer-memory)
[![CI/CD](https://img.shields.io/badge/CI%2FCD-passing-brightgreen.svg)](https://github.com/mergelord/claude-4layer-memory/actions)
[![Code Quality](https://img.shields.io/badge/code%20quality-10.0%2F10-brightgreen.svg)](https://github.com/mergelord/claude-4layer-memory)

---

## 🎯 Features

### Core Memory System
- **4-Layer Memory Architecture** - HOT (24h) → WARM (14d) → COLD (permanent) → SEMANTIC (indexed)
- **Dual-Level System** - Global memory (cross-project) + Project memory (project-specific)
- **Auto-Discovery** - Automatically detects and indexes projects
- **Smart Filtering** - Protects against indexing system directories (.git, node_modules, etc.)

### Advanced Search & Retrieval
- **Semantic Search** - Find information by meaning, not keywords (multilingual support)
- **Embedding Gateway** - Intelligent caching layer for embedding operations (reduces API costs by 70%)
- **Linguistic Triggers** - Automatic context retrieval on natural language signals (inspired by Claude Opus 4.7)
  - Possessive pronouns: "my project", "our code"
  - Definite articles: "the script", "the bug"
  - Past tense: "you recommended", "we discussed"
  - Bilingual: English + Russian support

> **Repository Tools (require full clone):** Hybrid search, BM25 ranking, parallel search, and cross-encoder reranking are development tools available in the repository but not included in the installed runtime.

### Quality Assurance & Monitoring
- **EncodingGate (URC-1)** - Automatic mojibake detection and repair for Cyrillic text
- **Health Monitoring** - Automatic rotation, corruption detection, size limits
- **System Artifacts Cleanup** - Intelligent removal of C--WINDOWS-system32 and similar artifacts
- **Skill Creator** - Automatic discovery and documentation of recurring patterns

> **Repository Tools (require full clone):** Memory Lint (two-layer validation system) is a development tool available in the repository but not included in the installed runtime.

### Reliability & Hardening
- **Timezone-Aware Cost Tracking** - All cost and usage timestamps are stored as timezone-aware UTC
- **Robust Cost Fallback** - Missing model prices no longer raise `KeyError`; pricing falls back safely
- **Unified Windows UTF-8 Guard** - Consistent UTF-8 stdout/stderr setup across all modules
- **BOM-Free UTF-8 Sources** - All sources are clean UTF-8 (no BOM), enforced by the EncodingGate
- **Path-Traversal Protection** - Unified key contract with path-traversal hardening for memory operations

> **Repository Tools (require full clone):** Sanitized FTS5 queries, graceful search degradation, and per-instance reranker caching are development features in the repository but not in the installed runtime.

### Developer Experience
- **Cross-Platform** - Windows, Linux, macOS support with platform-specific optimizations
- **MCP Server** - Model Context Protocol integration for IDE extensions
- **CLI Tools** - Comprehensive command-line interface for all operations
- **Cost Tracking** - Built-in token usage and cost monitoring
- **Code Quality** - Automated CI/CD with Pylint (10.0/10), MyPy, Ruff, Bandit, and Radon
  - Comprehensive automated test suite across Python 3.10-3.13 on Windows, Linux, and macOS (12 CI jobs)
  - Type safety with MyPy strict mode
  - Security scanning with Bandit
  - Complexity analysis with Radon
  - [See Code Quality Guide](docs/CODE_QUALITY.md)

---

## 📋 Table of Contents

- [Quick Start](#quick-start)
- [Installation](#installation)
- [Architecture](#architecture)
- [Usage](#usage)
- [Configuration](#configuration)
- [Examples](#examples)
- [Documentation](#documentation)
- [Contributing](#contributing)
- [Credits](#credits)
- [License](#license)

---

## 🚀 Quick Start

```bash
# Clone the repository
git clone https://github.com/mergelord/claude-4layer-memory.git
cd claude-4layer-memory

# IMPORTANT: Run pre-installation audit first
# Windows:
.\audit.bat

# Linux/Mac:
./audit.sh

# If audit passes, run installation
# Windows:
.\install.bat

# Linux/Mac:
./install.sh

# Verify installation
python scripts/l4_semantic_global.py stats
```

---

## 📦 Installation

> **Install from a git clone only.** This package is **not published to npm** (`"private": true` in `package.json`). All commands below assume you have cloned the repository and run them from its root. There is no `npm install` path.

### Prerequisites

- Python 3.10 or higher
- Claude Code CLI installed
- 500MB free disk space (for embeddings model)

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

### Manual Installation

1. Install Python dependencies:
```bash
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

2. Copy scripts to Claude hooks directory:
```bash
# Windows
copy scripts\*.py %USERPROFILE%\.claude\hooks\
copy scripts\windows\l4_*.bat %USERPROFILE%\.claude\hooks\

# Linux/Mac
cp scripts/*.py ~/.claude/hooks/
cp scripts/linux/l4_*.sh ~/.claude/hooks/
chmod +x ~/.claude/hooks/*.sh
```

3. Initialize memory structure from the bundled templates:
```bash
# Windows
copy templates\GLOBAL_PROJECTS.md.template %USERPROFILE%\.claude\GLOBAL_PROJECTS.md
copy templates\MEMORY.md.template %USERPROFILE%\.claude\memory\MEMORY.md
copy templates\handoff.md.template %USERPROFILE%\.claude\memory\handoff.md
copy templates\decisions.md.template %USERPROFILE%\.claude\memory\decisions.md

# Linux/Mac
cp templates/GLOBAL_PROJECTS.md.template ~/.claude/GLOBAL_PROJECTS.md
cp templates/MEMORY.md.template ~/.claude/memory/MEMORY.md
cp templates/handoff.md.template ~/.claude/memory/handoff.md
cp templates/decisions.md.template ~/.claude/memory/decisions.md
```

4. Build the semantic index:
```bash
python scripts/l4_semantic_global.py index-all
```

See [INSTALL.md](docs/INSTALL.md) for detailed instructions.

---

## 🏗️ Architecture

### 4-Layer Memory System

```
┌──────────────────────────────────────────────┐
│ Layer 4: SEMANTIC (Vector Search)                       │
│ ├─ ChromaDB + sentence-transformers                     │
│ └─ Multilingual semantic search                         │
├─────────────────────────────────────────────┤
│ Layer 3: COLD (Permanent Archive)                       │
│ ├─ archive/ directory                                   │
│ └─ Long-term storage                                    │
├─────────────────────────────────────────────┤
│ Layer 2: WARM (14 days)                                 │
│ ├─ decisions.md                                         │
│ └─ Important decisions, architectural choices           │
├─────────────────────────────────────────────┤
│ Layer 1: HOT (24 hours)                                 │
│ ├─ handoff.md                                           │
│ └─ Recent events, quick context recovery                │
└───────────────────────────────────────────────┘
```

### Dual-Level System

**Global Memory** (`~/.claude/memory/`)
- Cross-project knowledge
- Development style, principles
- User profile, global decisions

**Project Memory** (`~/.claude/projects/<project>/memory/`)
- Project-specific details
- Implementation decisions
- Project history

See [ARCHITECTURE.md](docs/architecture/ARCHITECTURE.md) for details.

---

## 💡 Usage

### Basic Commands

```bash
# Index all projects
l4_index_all.bat  # Windows
l4_index_all.sh   # Linux/Mac

# Search across all projects
l4_search_all.bat "semantic search query"

# Search in global memory only
l4_search_global.bat "coding style"

# View statistics
l4_stats.bat

# Cleanup junk collections
python l4_semantic_global.py cleanup --dry-run
python l4_semantic_global.py cleanup
```

### Repository Commands (require full clone)

```bash
# Validate memory health
python scripts/memory_lint.py --layer 1
```

### Adding New Project

1. Add project to `GLOBAL_PROJECTS.md`:
```markdown
### My New Project
**Path:** `C:\Projects\my-project`
**Memory:** `~/.claude/projects/C--Projects-my-project/memory/`
```

2. Reindex:
```bash
l4_index_all.bat
```

3. Done! Project is automatically discovered and indexed.

See [USAGE.md](docs/guides/USAGE.md) for more examples.

---

## ⚙️ Configuration

### GLOBAL_PROJECTS.md

Central registry of all projects:

```markdown
## Active Projects

### 1. Project Name
**Path:** `C:\path\to\project`
**Memory:** `~/.claude/projects/C--path-to-project/memory/`
**Status:** ✅ Active
```

### Memory Structure

Customize memory organization in each project:

```
memory/
├── MEMORY.md           # Index
├── handoff.md          # HOT layer
├── decisions.md        # WARM layer
├── archive/            # COLD layer
├── semantic_db/        # L4 layer
└── outputs/            # Reports
```

See [CONFIGURATION.md](docs/guides/CONFIGURATION.md) for details.

---

## 📚 Examples

### Installed Runtime Examples

These commands work from the installed hooks (`~/.claude/hooks/`) after running the installer:

#### Example 1: Cross-Project Learning

```bash
# Find solutions from other projects
l4_search_all.bat "how to handle Unicode errors"

# Results from multiple projects:
# [1] [project-A] decisions.md - Unicode handling solution
# [2] [project-B] feedback.md - Windows console encoding fix
```

#### Example 2: Project-Specific Search

```bash
# Search within a single project's memory
python scripts/l4_semantic_global.py search-project my-project "API integration"
```

#### Example 3: Health Check

```bash
# Check memory size / rotation health
python scripts/health_memory_size.py
```

### Repository Tools Examples

These commands require the full repository clone and are not available in the installed runtime:

#### Example 4: Parallel Hybrid Search

```bash
# Standard hybrid search (sequential)
python scripts/l4_fts5_search.py hybrid "memory system"

# Parallel hybrid search (2-3x faster)
python scripts/l4_fts5_search.py hybrid --parallel "memory system"

# Benchmark performance comparison
python scripts/benchmark_parallel_search.py "memory system"

# Output:
# Sequential (avg): 2.450s
# Parallel (avg):   0.890s
# Speedup: 2.75x
# Improvement: 63.7%
```

#### Example 5: Memory Lint Quick Check

```bash
# Quick check (SessionStart hook - fast)
python scripts/memory_lint.py --layer 1 --quick

# Full Layer 1 check
python scripts/memory_lint.py --layer 1

# Full check with semantic analysis
python scripts/memory_lint.py --layer all
```

See [examples/](examples/) directory for more.

---

## 📖 Documentation

- **[Installation Guide](docs/INSTALL.md)** - Detailed installation instructions
- **[Architecture Overview](docs/architecture/ARCHITECTURE.md)** - System design and components
- **[Usage Guide](docs/guides/USAGE.md)** - Commands and workflows
- **[Configuration Guide](docs/guides/CONFIGURATION.md)** - Customization options
- **[Memory Lint](docs/MEMORY_LINT.md)** - Memory validation and health checks
- **[EncodingGate](docs/ENCODING_GATE.md)** - Encoding validation and mojibake repair
- **[System Artifacts](docs/SYSTEM_ARTIFACTS.md)** - Understanding C--WINDOWS-system32 and cleanup
- **[P1: Embedding Gateway](docs/P1-Embedding-Gateway.md)** - Caching layer for embeddings
- **[Reranking](docs/RERANKING.md)** - Cross-encoder reranking system
- **[URC-1](docs/URC-1.md)** - Unicode Repair Contract specification
- **[API Reference](docs/api/API.md)** - Python API documentation
- **[FAQ](docs/FAQ.md)** - Frequently asked questions
- **[Troubleshooting](docs/TROUBLESHOOTING.md)** - Common issues and solutions

---

## 🤝 Contributing

Contributions are welcome! Please read [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

### Development Setup

```bash
# Clone repository
git clone https://github.com/mergelord/claude-4layer-memory.git
cd claude-4layer-memory

# Install dev dependencies
pip install -r requirements-dev.txt

# Run tests
python -m pytest tests/

# Run linters
python -m pylint scripts/*.py audit.py
python -m mypy scripts/ audit.py --explicit-package-bases
```

---

## 🙏 Credits

This project integrates ideas and concepts from multiple sources:

### Original Authors

- **[qwwiwi](https://github.com/qwwiwi)** - 4-layer memory architecture, HOT/WARM/COLD concept
  - [public-architecture-claude-code](https://github.com/qwwiwi/public-architecture-claude-code)
  - [architecture-brain-tests](https://github.com/qwwiwi/architecture-brain-tests)
  - [edgelab-install](https://github.com/qwwiwi/edgelab-install)
  - [independence-from-ai](https://github.com/qwwiwi/independence-from-ai)
  - [second-brain](https://github.com/qwwiwi/second-brain)

- **[cablate](https://github.com/cablate)** - Atomic wiki system for LLMs
  - [llm-atomic-wiki](https://github.com/cablate/llm-atomic-wiki)

### This Implementation

- **Project Contributors** - Integration, L4 SEMANTIC, auto-discovery, dual-level system, multilingual support, hybrid search, quality assurance

See [CREDITS.md](CREDITS.md) for detailed acknowledgments.

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## 🔗 Links

- **Documentation:** [https://github.com/mergelord/claude-4layer-memory](https://github.com/mergelord/claude-4layer-memory)
- **Issues:** [https://github.com/mergelord/claude-4layer-memory/issues](https://github.com/mergelord/claude-4layer-memory/issues)
- **Discussions:** [https://github.com/mergelord/claude-4layer-memory/discussions](https://github.com/mergelord/claude-4layer-memory/discussions)

---

## ⭐ Star History

If you find this project useful, please consider giving it a star!

---

**Made with ❤️ for the Claude Code community**
