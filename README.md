# Claude 4-Layer Memory System

**Intelligent memory management system for Claude Code with semantic search and cross-project knowledge sharing.**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.7+](https://img.shields.io/badge/python-3.7+-blue.svg)](https://www.python.org/downloads/)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey.svg)](https://github.com/mergelord/claude-4layer-memory)

---

## 🌟 Features

- **4-Layer Memory Architecture** - HOT (24h) → WARM (14d) → COLD (permanent) → SEMANTIC (indexed)
- **Dual-Level System** - Global memory (cross-project) + Project memory (project-specific)
- **Semantic Search** - Find information by meaning, not keywords (multilingual support)
- **Memory Lint** - Two-layer validation with quick mode for SessionStart hooks
- **Auto-Discovery** - Automatically detects and indexes projects
- **Smart Filtering** - Protects against indexing system directories
- **Health Monitoring** - Automatic rotation, corruption detection
- **Cross-Platform** - Windows, Linux, macOS support
- **Code Quality** - Automated CI/CD with Pylint, MyPy, Ruff, Bandit, and Radon ([See Code Quality Guide](docs/CODE_QUALITY.md))

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

### Prerequisites

- Python 3.7 or higher
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
pip install chromadb sentence-transformers
```

2. Copy scripts to Claude hooks directory:
```bash
# Windows
copy scripts\*.py %USERPROFILE%\.claude\hooks\
copy scripts\windows\*.bat %USERPROFILE%\.claude\hooks\

# Linux/Mac
cp scripts/*.py ~/.claude/hooks/
cp scripts/linux/*.sh ~/.claude/hooks/
chmod +x ~/.claude/hooks/*.sh
```

3. Initialize memory structure:
```bash
python scripts/setup_l4_project.py
```

See [INSTALL.md](docs/INSTALL.md) for detailed instructions.

---

## 🏗️ Architecture

### 4-Layer Memory System

```
┌─────────────────────────────────────────────────────────┐
│ Layer 4: SEMANTIC (Vector Search)                       │
│ ├─ ChromaDB + sentence-transformers                     │
│ └─ Multilingual semantic search                         │
├─────────────────────────────────────────────────────────┤
│ Layer 3: COLD (Permanent Archive)                       │
│ ├─ archive/ directory                                   │
│ └─ Long-term storage                                    │
├─────────────────────────────────────────────────────────┤
│ Layer 2: WARM (14 days)                                 │
│ ├─ decisions.md                                         │
│ └─ Important decisions, architectural choices           │
├─────────────────────────────────────────────────────────┤
│ Layer 1: HOT (24 hours)                                 │
│ ├─ handoff.md                                           │
│ └─ Recent events, quick context recovery                │
└─────────────────────────────────────────────────────────┘
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

# Validate memory health
memory_lint.bat  # Windows
memory_lint.sh   # Linux/Mac
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

### Example 1: Cross-Project Learning

```bash
# Find solutions from other projects
l4_search_all.bat "how to handle Unicode errors"

# Results from multiple projects:
# [1] [project-A] decisions.md - Unicode handling solution
# [2] [project-B] feedback.md - Windows console encoding fix
```

### Example 2: Project-Specific Search

```bash
# Search only in current project
l4_search.bat "API integration"
```

### Example 3: Memory Lint Quick Check

```bash
# Quick check (SessionStart hook - fast)
python scripts/memory_lint.py --layer 1 --quick

# Full Layer 1 check
python scripts/memory_lint.py --layer 1

# Full check with semantic analysis
python scripts/memory_lint.py --layer all
```

### Example 4: Health Check

```bash
# Check memory system health
python memory_health_check.py

# Output:
# ✓ HOT memory: 3 entries (within 24h window)
# ✓ WARM memory: 12 entries (within 14d window)
# ✓ L4 index: 489 chunks across 3 collections
```

See [examples/](examples/) directory for more.

---

## 📖 Documentation

- **[Installation Guide](docs/INSTALL.md)** - Detailed installation instructions
- **[Architecture Overview](docs/architecture/ARCHITECTURE.md)** - System design and components
- **[Usage Guide](docs/guides/USAGE.md)** - Commands and workflows
- **[Configuration Guide](docs/guides/CONFIGURATION.md)** - Customization options
- **[Memory Lint](docs/MEMORY_LINT.md)** - Memory validation and health checks
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

- **MYRIG** - Integration, L4 SEMANTIC, auto-discovery, dual-level system, multilingual support

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
