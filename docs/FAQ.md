# Frequently Asked Questions (FAQ)

## Table of Contents

- [General Questions](#general-questions)
- [Installation & Setup](#installation--setup)
- [Usage & Features](#usage--features)
- [Performance & Optimization](#performance--optimization)
- [Troubleshooting](#troubleshooting)
- [Advanced Topics](#advanced-topics)

---

## General Questions

### What is Claude 4-Layer Memory System?

Claude 4-Layer Memory System is an enterprise-grade memory management solution for Claude Code that provides:
- **4-layer architecture** (HOT/WARM/COLD/SEMANTIC) for efficient memory organization
- **Hybrid search** combining semantic, BM25, and FTS5 with RRF fusion
- **Cross-project knowledge sharing** through global memory
- **Automatic quality assurance** with Memory Lint and EncodingGate

### Who should use this system?

This system is ideal for:
- Developers working on multiple projects with Claude Code
- Teams needing consistent memory management across projects
- Users who want semantic search capabilities
- Anyone looking for enterprise-grade quality assurance

### What are the system requirements?

- **Python:** 3.10 or higher
- **Disk Space:** ~500MB for embedding model (first time)
- **RAM:** 2GB minimum, 4GB recommended
- **OS:** Windows, Linux, or macOS

---

## Installation & Setup

### How do I install the system?

1. Run pre-installation audit:
   ```bash
   # Windows
   .\audit.bat
   
   # Linux/Mac
   ./audit.sh
   ```

2. If audit passes, run installation:
   ```bash
   # Windows
   .\install.bat
   
   # Linux/Mac
   ./install.sh
   ```

See [INSTALL.md](INSTALL.md) for detailed instructions.

### Do I need to install anything manually?

No! The installation script automatically:
- Installs Python dependencies
- Downloads the embedding model
- Sets up directory structure
- Configures hooks

### Can I use this with existing Claude Code projects?

Yes! The system:
- Preserves existing memory files
- Works alongside your current setup
- Provides migration tools if needed

### Where are files installed?

- **Scripts:** `~/.claude/hooks/`
- **Global memory:** `~/.claude/memory/`
- **Project memory:** `~/.claude/projects/<project>/memory/`
- **Configuration:** `~/.claude/GLOBAL_PROJECTS.md`

---

## Usage & Features

### How do I add a new project?

1. Edit `~/.claude/GLOBAL_PROJECTS.md`:
   ```markdown
   ### My Project
   **Path:** `/path/to/project`
   **Memory:** `~/.claude/projects/path-to-project/memory/`
   **Status:** ✅ Active
   ```

2. Reindex:
   ```bash
   l4_index_all.bat  # Windows
   l4_index_all.sh   # Linux/Mac
   ```

### What's the difference between global and project memory?

- **Global memory** (`~/.claude/memory/`):
  - Cross-project knowledge
  - Development principles
  - User preferences
  - Shared patterns

- **Project memory** (`~/.claude/projects/<project>/memory/`):
  - Project-specific details
  - Implementation decisions
  - Project history
  - Local context

### How does semantic search work?

Semantic search uses sentence-transformers to:
1. Convert text to embeddings (vector representations)
2. Find similar content by meaning, not just keywords
3. Support multilingual queries (English + Russian)
4. Cache embeddings for performance

Example:
```bash
# These queries find similar results:
l4_search_all.bat "error handling"
l4_search_all.bat "exception management"
l4_search_all.bat "обработка ошибок"  # Russian
```

### What is hybrid search?

Hybrid search combines three ranking methods:
- **Semantic:** Meaning-based similarity
- **BM25:** Probabilistic keyword ranking
- **FTS5:** Full-text search

Results are merged using Reciprocal Rank Fusion (RRF) and reranked with a cross-encoder for optimal relevance.

### How often should I reindex?

Reindex when:
- Adding new projects
- Making significant memory changes
- After bulk updates
- Weekly for active projects

Quick reindex: `l4_index_all.bat` (takes 1-5 minutes)

---

## Performance & Optimization

### Why is the first search slow?

The first search downloads the embedding model (~500MB). Subsequent searches are fast due to:
- Model caching
- Embedding caching (70% cost reduction)
- Parallel search execution

### How can I improve search performance?

1. **Use parallel search** (enabled by default):
   ```python
   memory.search_all("query", n_results=10)  # Uses ThreadPoolExecutor
   ```

2. **Limit result count**:
   ```bash
   l4_search_all.bat "query" 5  # Only top 5 results
   ```

3. **Use quick mode for validation**:
   ```bash
   python scripts/memory_lint.py --quick
   ```

### How much disk space does indexing use?

- **Small project** (10 files): ~1MB
- **Medium project** (100 files): ~10MB
- **Large project** (1000 files): ~100MB

Embeddings are compressed and deduplicated.

### Can I run this on a low-end machine?

Yes! The system is optimized for:
- Minimal RAM usage (2GB minimum)
- Efficient disk I/O
- Optional quick modes
- Incremental indexing

---

## Troubleshooting

### Search returns no results

**Possible causes:**
1. Project not indexed: Run `l4_index_all.bat`
2. Empty memory files: Add content to memory/
3. Query too specific: Try broader terms

**Solution:**
```bash
# Check index status
python scripts/l4_semantic_global.py stats

# Reindex if needed
l4_index_all.bat
```

### "Collection not found" error

**Cause:** Project not in GLOBAL_PROJECTS.md or not indexed

**Solution:**
1. Add project to `~/.claude/GLOBAL_PROJECTS.md`
2. Run `l4_index_all.bat`

### Encoding errors (mojibake)

**Cause:** Windows console encoding issues with Cyrillic text

**Solution:**
```bash
# Scan for issues
python scripts/memory_lint.py --validate-encoding

# Auto-repair
python scripts/memory_lint.py --repair-mojibake --apply
```

### Memory Lint fails

**Common issues:**
- Ghost links: Update or remove broken links
- Old HOT entries: Archive entries older than 24h
- Large files: Split files >100KB

**Quick fix:**
```bash
python scripts/memory_lint.py --quick  # Fast check
python scripts/memory_lint.py --layer 1  # Full Layer 1
```

### Installation fails

**Check:**
1. Python version: `python --version` (need 3.10+)
2. Pip works: `pip --version`
3. Internet connection (for model download)
4. Disk space: ~500MB free

**Get help:**
```bash
python audit.py  # Detailed diagnostics
```

---

## Advanced Topics

### Can I customize the embedding model?

Yes! Edit `scripts/l4_semantic_global.py`:
```python
MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"  # Default
# Or use:
# MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
```

### How do I integrate with VS Code?

Use the MCP (Model Context Protocol) server:
```bash
python mcp_server.py
```

See [MCP_SERVER.md](MCP_SERVER.md) for details.

### Can I use this in CI/CD?

Yes! Example GitHub Actions:
```yaml
- name: Validate Memory
  run: |
    python scripts/memory_lint.py --quick
    python scripts/memory_lint.py --validate-encoding
```

See [.github/workflows/](../.github/workflows/) for examples.

### How do I backup my memory?

**Manual backup:**
```bash
# Backup global memory
cp -r ~/.claude/memory ~/.claude/memory.backup

# Backup all projects
cp -r ~/.claude/projects ~/.claude/projects.backup
```

**Automated backup:**
Add to cron/Task Scheduler:
```bash
0 2 * * * tar -czf ~/backups/claude-memory-$(date +\%Y\%m\%d).tar.gz ~/.claude/memory
```

### Can I use this with multiple Claude instances?

Yes! Each instance can have its own:
- GLOBAL_PROJECTS.md
- Memory directories
- Configuration

Set `CLAUDE_HOME` environment variable to separate instances.

### How do I contribute?

See [CONTRIBUTING.md](CONTRIBUTING.md) for:
- Code style guidelines
- Testing requirements
- Pull request process
- Development setup

---

## Still Have Questions?

- **Documentation:** [docs/](.)
- **Issues:** [GitHub Issues](https://github.com/mergelord/claude-4layer-memory/issues)
- **Discussions:** [GitHub Discussions](https://github.com/mergelord/claude-4layer-memory/discussions)

---

**Last Updated:** 2026-05-22  
**Version:** 1.4.0