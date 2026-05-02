# Claude 4-Layer Memory System

This file provides guidance for Claude Code when working with this project.

## Overview

**Claude 4-Layer Memory System** is an intelligent memory management system for Claude Code that provides semantic search, cross-project knowledge sharing, and automated context management through a 4-layer architecture (HOT → WARM → COLD → SEMANTIC).

**Version:** 1.3.1  
**Status:** Production (published on GitHub)  
**License:** MIT

## Project Structure

```
claude-4layer-memory/
├── scripts/                    # Core Python modules
│   ├── memory_lint.py         # Two-layer validation system
│   ├── l4_semantic_global.py  # Semantic search engine
│   ├── l4_fts5_search.py      # FTS5 keyword search
│   ├── show_global_context.py # SessionStart hook
│   ├── stop_handoff_universal.py # Stop hook
│   ├── memory_lint_helpers.py # Validation helpers (EncodingGate)
│   └── semantic_search.py     # ChromaDB integration
├── tests/                      # Pytest test suite
├── docs/                       # Documentation
├── deploy/                     # Installation scripts
├── cli/                        # CLI interface
├── utils/                      # Utility functions
├── requirements.txt            # Production dependencies
├── requirements-dev.txt        # Development dependencies
└── README.md                   # User documentation
```

## Tech Stack

**Core:**
- Python 3.10+ (type hints required)
- ChromaDB 0.4.0+ (vector database for semantic search)
- SQLite FTS5 (full-text search)
- sentence-transformers 2.2.0+ (embeddings)

**Development:**
- pytest 7.0+ (testing framework)
- ruff (linting and formatting)
- mypy (type checking)
- bandit (security scanning)
- radon (complexity analysis)

**CI/CD:**
- GitHub Actions (automated testing)
- Pre-commit hooks (code quality)

## Setup & Installation

### For Contributors

1. **Clone and setup:**
```bash
git clone https://github.com/mergelord/claude-4layer-memory.git
cd claude-4layer-memory
```

2. **Run pre-installation audit:**
```bash
# Windows
.\audit.bat

# Linux/macOS
./audit.sh
```

3. **Install dependencies:**
```bash
pip install -r requirements-dev.txt
```

4. **Run tests:**
```bash
pytest tests/ -v
```

5. **Verify installation:**
```bash
python scripts/l4_semantic_global.py stats
```

### Development Environment

- **Python version:** 3.10+ required
- **Virtual environment:** Recommended (venv or conda)
- **IDE:** VS Code or PyCharm recommended
- **Git hooks:** Installed automatically by install scripts

## Architecture

### 4-Layer Memory System

**HOT Layer (24h retention):**
- Recent events and session handoffs
- File: `memory/handoff.md`
- Auto-rotation after 24 hours

**WARM Layer (14d retention):**
- Important decisions and milestones
- File: `memory/decisions.md`
- Manual curation recommended

**COLD Layer (permanent):**
- Long-term knowledge and patterns
- Directory: `memory/archive/`
- Organized by topic

**SEMANTIC Layer (indexed):**
- Vector embeddings for semantic search
- ChromaDB collection
- Multilingual support (English + Russian)

### Dual-Level System

**Global Memory:**
- Location: `~/.claude/memory/`
- Scope: Cross-project knowledge
- Use: Shared patterns, user preferences

**Project Memory:**
- Location: `~/.claude/projects/<project-path>/memory/`
- Scope: Project-specific context
- Use: Project decisions, architecture notes

### Key Components

**Memory Lint (`scripts/memory_lint.py`):**
- Two-layer validation (quick + full mode)
- Ghost link detection
- Encoding validation (EncodingGate)
- Frontmatter validation
- Usage: `python scripts/memory_lint.py --quick`

**Semantic Search (`scripts/l4_semantic_global.py`):**
- ChromaDB-powered vector search
- Multilingual embeddings
- Auto-discovery of projects
- Usage: `python scripts/l4_semantic_global.py search "your query"`

**FTS5 Search (`scripts/l4_fts5_search.py`):**
- SQLite full-text search
- Keyword-based queries
- Fast indexing
- Usage: `python scripts/l4_fts5_search.py search "keyword"`

**SessionStart Hook (`scripts/show_global_context.py`):**
- Loads context at session start
- Displays recent events
- Runs memory lint quick check

**Stop Hook (`scripts/stop_handoff_universal.py`):**
- Saves session summary
- Updates handoff.md
- Triggers memory rotation

## Development Workflow

### Code Style

- **Naming:** snake_case for Python
- **Line length:** 100 characters max
- **Type hints:** Required for all functions
- **Docstrings:** Google style
- **Imports:** stdlib → third-party → local

### Testing Requirements

**Before committing:**
1. Run full test suite: `pytest tests/ -v`
2. Check coverage: `pytest --cov=scripts tests/`
3. Run linter: `ruff check .`
4. Run type checker: `mypy scripts/`
5. Security scan: `bandit -r scripts/`

**Test structure:**
- Unit tests: `tests/test_*.py`
- Integration tests: `tests/integration/`
- Fixtures: `tests/conftest.py`

### Git Workflow

**Branches:**
- `main` - production releases
- `feature/*` - new features
- `fix/*` - bug fixes
- `refactor/*` - code improvements

**Commits:**
- Language: Russian (project convention)
- Format: `<type>: <description>`
- Types: feat, fix, refactor, test, docs, chore

**Pull Requests:**
- Required: Tests passing, code review
- Template: `.github/PULL_REQUEST_TEMPLATE.md`
- CI checks: All must pass

### Code Quality Standards

**Complexity limits:**
- Cyclomatic Complexity: <10 per function
- Maintainability Index: >65
- Cognitive Complexity: <15

**Security:**
- No hardcoded secrets
- Input validation required
- SQL injection prevention (parameterized queries)
- Path traversal protection

## File Structure Explanations

### Core Scripts

**`scripts/memory_lint.py`** (43KB, 1000+ lines)
- Two-layer validation system
- Quick mode for SessionStart hooks
- Full mode for deep validation
- EncodingGate integration for mojibake detection

**`scripts/l4_semantic_global.py`** (40KB, 900+ lines)
- Semantic search engine
- ChromaDB collection management
- Auto-discovery of projects
- Multilingual embeddings

**`scripts/l4_fts5_search.py`** (18KB, 400+ lines)
- SQLite FTS5 integration
- Keyword search
- Fast indexing
- Hybrid search support

**`scripts/memory_lint_helpers.py`** (23KB, 500+ lines)
- EncodingGate class (mojibake detection)
- Validation utilities
- Regex patterns
- Helper functions

**`scripts/show_global_context.py`**
- SessionStart hook implementation
- Context loading
- Memory lint quick check

**`scripts/stop_handoff_universal.py`**
- Stop hook implementation
- Session summary generation
- Handoff.md updates

### Configuration Files

**`requirements.txt`**
- Production dependencies
- Pinned versions for stability

**`requirements-dev.txt`**
- Development dependencies
- Testing and linting tools

**`.gitignore`**
- Excludes: `__pycache__/`, `.pytest_cache/`, `*.pyc`
- Protects: Personal memory files, API keys

## Common Tasks

### Adding a New Feature

1. Create feature branch: `git checkout -b feature/your-feature`
2. Write tests first (TDD approach)
3. Implement feature
4. Run full test suite
5. Update documentation
6. Create pull request

### Fixing a Bug

1. Write failing test reproducing the bug
2. Fix the bug
3. Verify test passes
4. Run full test suite
5. Create pull request with `fix/` prefix

### Refactoring Code

1. Ensure tests exist and pass
2. Refactor code
3. Verify tests still pass
4. Check complexity metrics improved
5. Create pull request with `refactor/` prefix

### Running Memory Lint

```bash
# Quick check (for SessionStart hooks)
python scripts/memory_lint.py --quick

# Full validation
python scripts/memory_lint.py

# Validate encoding
python scripts/memory_lint.py --validate-encoding

# Repair mojibake
python scripts/memory_lint.py --repair-mojibake --apply
```

### Running Semantic Search

```bash
# Search global memory
python scripts/l4_semantic_global.py search "your query"

# Reindex projects
python scripts/l4_semantic_global.py reindex

# Show statistics
python scripts/l4_semantic_global.py stats
```

## Important Notes

### Memory System Protocol

- **HOT layer** rotates automatically after 24h
- **WARM layer** requires manual curation
- **COLD layer** is permanent, organize by topic
- **SEMANTIC layer** auto-indexes on changes

### Encoding Handling

- **EncodingGate** prevents mojibake before writing
- Use `assert_clean()` before file writes
- Use `scan_file()` for validation
- Use `repair_mojibake()` for recovery

### Cross-Platform Compatibility

- Use `pathlib.Path` for file paths
- Test on Windows, Linux, macOS
- Handle line endings (CRLF vs LF)
- Respect platform-specific conventions

### Performance Considerations

- ChromaDB indexing can be slow on first run
- FTS5 search is faster for keyword queries
- Memory lint quick mode for SessionStart hooks
- Batch operations when possible

## Troubleshooting

### Common Issues

**ChromaDB not found:**
```bash
pip install chromadb>=0.4.0
```

**Encoding errors:**
```bash
python scripts/memory_lint.py --repair-mojibake --apply
```

**Tests failing:**
```bash
pytest tests/ -v --tb=short
```

**Import errors:**
```bash
# Ensure scripts/ is in PYTHONPATH
export PYTHONPATH="${PYTHONPATH}:$(pwd)/scripts"
```

## Contributing

We welcome contributions! Please:

1. Read `CONTRIBUTING.md` (if exists)
2. Follow code style guidelines
3. Write tests for new features
4. Update documentation
5. Create descriptive pull requests

## Resources

- **GitHub:** https://github.com/mergelord/claude-4layer-memory
- **Issues:** https://github.com/mergelord/claude-4layer-memory/issues
- **Documentation:** `docs/` directory
- **Code Quality:** `docs/CODE_QUALITY.md`

## Version

**Current:** 1.3.1  
**Last Updated:** 2026-05-01  
**Changelog:** See `CHANGELOG.md`
