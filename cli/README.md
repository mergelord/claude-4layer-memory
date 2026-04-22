# claude-memory-cli

CLI tool for Claude 4-Layer Memory System - intelligent memory management with semantic search.

## Installation

### Global installation (recommended)

```bash
npm install -g claude-memory-cli
```

### Local installation

```bash
npm install claude-memory-cli
```

### From source

```bash
git clone https://github.com/mergelord/claude-4layer-memory.git
cd claude-4layer-memory
npm install
npm link
```

## Usage

### Quick start

```bash
# Show help
claude-memory-cli --help

# Or use short alias
cm --help
```

### Commands

#### 1. Initialize memory system

```bash
claude-memory-cli init
```

Initializes the memory system in the current directory.

#### 2. Search memory

```bash
# Search all memory (global + project)
claude-memory-cli search "python testing"

# Search global memory only
claude-memory-cli search "python testing" --global

# Search project memory only
claude-memory-cli search "python testing" --project

# Limit results
claude-memory-cli search "python testing" --limit 5
```

Uses hybrid search (FTS5 keyword + semantic search) for best results.

#### 3. Validate memory

```bash
# Quick validation (Layer 1 only)
claude-memory-cli lint --quick

# Full validation (Layer 1 + 2)
claude-memory-cli lint

# Pre-delivery checklist
claude-memory-cli lint --checklist
```

Validates memory structure, detects anti-patterns, and ensures quality.

#### 4. Create memory

```bash
# Interactive mode
claude-memory-cli build

# With options
claude-memory-cli build --type feedback --name testing_workflow
```

Creates a new memory file with proper frontmatter and updates the index.

#### 5. Show statistics

```bash
claude-memory-cli stats
```

Displays memory statistics, storage usage, and index status.

## Features

- ✅ **Hybrid Search** - FTS5 keyword + semantic search
- ✅ **Memory Validation** - 2-layer lint with anti-patterns detection
- ✅ **Pre-Delivery Checklist** - Quality checks before commit
- ✅ **Interactive Builder** - Easy memory creation
- ✅ **Statistics** - Memory usage and index status
- ✅ **Cross-platform** - Windows, Linux, macOS

## Requirements

- Node.js >= 14.0.0
- Python 3.10+ (for backend scripts)

## Integration

### Pre-commit hook

Add to `.git/hooks/pre-commit`:

```bash
#!/bin/bash
claude-memory-cli lint --quick || exit 1
```

### CI/CD

```yaml
- name: Validate memory
  run: |
    npm install -g claude-memory-cli
    claude-memory-cli lint --checklist
```

## License

MIT

## Repository

https://github.com/mergelord/claude-4layer-memory

## Issues

https://github.com/mergelord/claude-4layer-memory/issues
