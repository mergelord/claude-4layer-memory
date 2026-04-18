# Configuration Guide

Complete configuration reference for Claude 4-Layer Memory System.

---

## Table of Contents

- [Overview](#overview)
- [GLOBAL_PROJECTS.md](#global_projectsmd)
- [Memory Structure](#memory-structure)
- [Environment Variables](#environment-variables)
- [Advanced Configuration](#advanced-configuration)
- [Customization](#customization)

---

## Overview

Claude 4-Layer Memory System uses file-based configuration with sensible defaults. Most users only need to configure `GLOBAL_PROJECTS.md`.

**Configuration Files:**
- `~/.claude/GLOBAL_PROJECTS.md` - Project registry (required)
- `~/.claude/memory/` - Global memory structure
- `~/.claude/projects/<project>/memory/` - Project memory structure

---

## GLOBAL_PROJECTS.md

Central registry of all projects. Used by L4 SEMANTIC for auto-discovery.

### Location

**Windows:** `%USERPROFILE%\.claude\GLOBAL_PROJECTS.md`  
**Linux/Mac:** `~/.claude/GLOBAL_PROJECTS.md`

### Format

```markdown
# Global Projects Registry

**Last Updated:** 2026-04-18

---

## Active Projects

### 1. Project Name
**Path:** `/path/to/project`
**Memory:** `~/.claude/projects/encoded-path/memory/`
**Status:** ✅ Active

**Description:**
Brief project description.

**Key Components:**
- Component 1
- Component 2

**Last Changes:**
- Recent change 1
```

### Required Fields

| Field | Description | Example |
|-------|-------------|---------|
| **Path** | Absolute path to project | `/home/user/projects/my-app` |
| **Memory** | Path to project memory | `~/.claude/projects/my-app/memory/` |
| **Status** | Project status | ✅ Active, 🔄 In Development, 📦 Archived |

### Memory Path Encoding

Convert project path to memory path:

**Rules:**
1. Replace `/` with `-`
2. Replace `:` with `--`
3. Replace spaces with `-`
4. Remove leading `/`

**Examples:**

| Project Path | Memory Path |
|--------------|-------------|
| `/home/user/projects/app` | `home-user-projects-app` |
| `C:\Projects\MyApp` | `C--Projects-MyApp` |
| `/Users/name/my project` | `Users-name-my-project` |

### Status Icons

| Icon | Status | Meaning |
|------|--------|---------|
| ✅ | Active | Currently working on |
| 🔄 | In Development | Active development |
| 📦 | Archived | No longer active |
| ⚠️ | Deprecated | Being phased out |
| 🚀 | Production | Live in production |

### Example Configuration

```markdown
## Active Projects

### 1. Web Application
**Path:** `/home/user/projects/webapp`
**Memory:** `~/.claude/projects/home-user-projects-webapp/memory/`
**Status:** ✅ Active

**Description:**
Main web application with React frontend and Node.js backend.

**Key Components:**
- React 18 frontend
- Express.js API
- PostgreSQL database
- Redis cache

**Last Changes:**
- Added authentication system (2026-04-15)
- Migrated to TypeScript (2026-04-10)

---

### 2. Mobile App
**Path:** `/home/user/projects/mobile`
**Memory:** `~/.claude/projects/home-user-projects-mobile/memory/`
**Status:** 🔄 In Development

**Description:**
React Native mobile application.

---

### 3. Legacy System
**Path:** `/home/user/projects/legacy`
**Memory:** `~/.claude/projects/home-user-projects-legacy/memory/`
**Status:** 📦 Archived

**Description:**
Old system, kept for reference only.
```

---

## Memory Structure

### Global Memory

**Location:** `~/.claude/memory/`

**Structure:**
```
memory/
├── MEMORY.md              # Index file
├── handoff.md             # HOT layer (24h)
├── decisions.md           # WARM layer (14d)
├── archive/               # COLD layer (permanent)
│   ├── 2026-04/
│   ├── 2026-03/
│   └── 2026-02/
├── outputs/               # Generated reports
├── user_profile.md        # User preferences
├── feedback_*.md          # Feedback memories
├── project_overview.md    # Project summaries
└── reference_*.md         # Reference materials
```

### Project Memory

**Location:** `~/.claude/projects/<project>/memory/`

**Structure:**
```
memory/
├── MEMORY.md              # Project index
├── handoff.md             # Project HOT layer
├── decisions.md           # Project WARM layer
├── archive/               # Project COLD layer
├── semantic_db/           # L4 vector database
├── outputs/               # Project reports
├── feedback_*.md          # Project feedback
└── project_*.md           # Project details
```

### Memory File Templates

#### MEMORY.md

```markdown
# Memory Index

## User
- [User Profile](user_profile.md)

## Feedback
- [Development Style](feedback_style.md)

## Project
- [Overview](project_overview.md)

## Reference
- [Resources](reference_resources.md)
```

#### handoff.md

```markdown
# HOT Memory - Handoff

**Last Updated:** [DATE]

---

## Events

### [TIMESTAMP] - Event Title
**What happened:** Description
**Context:** Relevant context
**Next steps:** What to do next
```

#### decisions.md

```markdown
# WARM Memory - Decisions

**Last Updated:** [DATE]

---

## Decisions

### Decision Title
**Decision:** What was decided
**Reason:** Why
**Date:** [DATE]

**Why:**
- Reasoning

**How to apply:**
- Guidelines
```

---

## Environment Variables

### L4_MODEL

Override default embedding model.

**Default:** `paraphrase-multilingual-MiniLM-L12-v2`

**Usage:**
```bash
export L4_MODEL="sentence-transformers/all-MiniLM-L6-v2"
python l4_semantic_global.py index-all
```

**Available models:**
- `paraphrase-multilingual-MiniLM-L12-v2` (default, multilingual)
- `all-MiniLM-L6-v2` (English only, faster)
- `all-mpnet-base-v2` (English only, more accurate)

### HF_TOKEN

HuggingFace API token (optional).

**Purpose:** Faster model downloads, higher rate limits

**Usage:**
```bash
export HF_TOKEN="your_token_here"
```

**Get token:** https://huggingface.co/settings/tokens

---

## Advanced Configuration

### Custom Memory Locations

**Override global memory:**
```bash
# Not recommended, but possible
export CLAUDE_MEMORY_DIR="/custom/path/memory"
```

### Custom Database Location

**Override semantic DB:**
```bash
# Not recommended, but possible
export CLAUDE_SEMANTIC_DB="/custom/path/semantic_db"
```

### Indexing Options

**Chunk size:**

Edit `l4_semantic_global.py`:
```python
def _split_into_chunks(self, content: str, max_chunk_size: int = 500):
    # Change 500 to your preferred size
```

**Smaller chunks:** More precise search, larger database  
**Larger chunks:** More context, smaller database

### Search Options

**Number of results:**

```bash
# Default: 10 results
python l4_semantic_global.py search-all "query"

# Custom: Edit script or use Python API
```

---

## Customization

### Adding Custom Memory Types

1. **Create new memory file:**
```bash
touch ~/.claude/memory/custom_type.md
```

2. **Add to MEMORY.md:**
```markdown
## Custom
- [Custom Type](custom_type.md) — Description
```

3. **Use frontmatter:**
```markdown
---
name: custom_type
description: Custom memory type
type: custom
---

# Custom Memory

Content here...
```

### Custom Filters

**Edit `l4_semantic_global.py`:**

```python
def _discover_projects(self) -> list:
    # Add custom filtering logic
    if "test" in project_dir.name.lower():
        print(f"[SKIP] Test project: {project_dir.name}")
        continue
```

### Custom Hooks

**Session start hook:**
```bash
# ~/.claude/hooks/session-start.sh
#!/bin/bash
# Auto-index on session start
l4_index_all.sh > /dev/null 2>&1 &
```

**Session stop hook:**
```bash
# ~/.claude/hooks/session-stop.sh
#!/bin/bash
# Auto-index on session end
l4_index_all.sh > /dev/null 2>&1
```

---

## Configuration Examples

### Example 1: Single Project Setup

**GLOBAL_PROJECTS.md:**
```markdown
### My Project
**Path:** `/home/user/my-project`
**Memory:** `~/.claude/projects/home-user-my-project/memory/`
**Status:** ✅ Active
```

**Memory structure:**
```
~/.claude/
├── GLOBAL_PROJECTS.md
├── memory/
│   ├── MEMORY.md
│   ├── handoff.md
│   └── decisions.md
└── projects/
    └── home-user-my-project/
        └── memory/
            ├── MEMORY.md
            ├── handoff.md
            ├── decisions.md
            └── semantic_db/
```

### Example 2: Multi-Project Setup

**GLOBAL_PROJECTS.md:**
```markdown
### Frontend
**Path:** `/home/user/frontend`
**Memory:** `~/.claude/projects/home-user-frontend/memory/`
**Status:** ✅ Active

### Backend
**Path:** `/home/user/backend`
**Memory:** `~/.claude/projects/home-user-backend/memory/`
**Status:** ✅ Active

### Mobile
**Path:** `/home/user/mobile`
**Memory:** `~/.claude/projects/home-user-mobile/memory/`
**Status:** 🔄 In Development
```

### Example 3: Team Setup

**Shared GLOBAL_PROJECTS.md (in git):**
```markdown
### Team Project
**Path:** `/team/shared/project`
**Memory:** `~/.claude/projects/team-shared-project/memory/`
**Status:** ✅ Active
```

**Individual memory:** Each team member has their own `~/.claude/memory/`

---

## Best Practices

### 1. Keep GLOBAL_PROJECTS.md Updated

✅ **Do:**
- Update immediately when adding projects
- Mark inactive projects
- Remove deleted projects
- Keep descriptions current

❌ **Don't:**
- Leave outdated projects
- Forget to update memory paths
- Use relative paths

### 2. Organize Memory Files

✅ **Do:**
- Use descriptive filenames
- Add frontmatter metadata
- Keep files focused
- Archive old content

❌ **Don't:**
- Create huge monolithic files
- Mix unrelated content
- Forget to update MEMORY.md index

### 3. Regular Maintenance

**Weekly:**
- Review GLOBAL_PROJECTS.md
- Check memory file sizes
- Run cleanup: `l4_cleanup.sh`

**Monthly:**
- Archive old decisions
- Review and update descriptions
- Check disk space

### 4. Backup Strategy

**What to backup:**
- ✅ `~/.claude/GLOBAL_PROJECTS.md`
- ✅ `~/.claude/memory/` (except semantic_db)
- ✅ `~/.claude/projects/*/memory/` (except semantic_db)

**What NOT to backup:**
- ❌ `semantic_db/` (can be regenerated)
- ❌ `*.sqlite3` (can be regenerated)

**Backup command:**
```bash
tar -czf claude-memory-backup.tar.gz \
    --exclude='semantic_db' \
    --exclude='*.sqlite3' \
    ~/.claude/memory \
    ~/.claude/projects/*/memory \
    ~/.claude/GLOBAL_PROJECTS.md
```

---

## Troubleshooting Configuration

### Projects not discovered

**Problem:** L4 doesn't find projects

**Check:**
1. GLOBAL_PROJECTS.md exists
2. Memory path format is correct
3. Memory directory exists
4. Run with verbose output

### Wrong memory path

**Problem:** Memory path doesn't match project

**Solution:**
1. Check encoding rules
2. Verify path in GLOBAL_PROJECTS.md
3. Create directory if missing

### Indexing fails

**Problem:** Indexing errors

**Check:**
1. Memory files are valid markdown
2. No corrupted files
3. Sufficient disk space
4. Python dependencies installed

---

## Next Steps

- **Usage Examples:** See [USAGE.md](USAGE.md)
- **Architecture:** See [ARCHITECTURE.md](../architecture/ARCHITECTURE.md)
- **Troubleshooting:** See [TROUBLESHOOTING.md](../TROUBLESHOOTING.md)

---

**Configuration complete! Start using Claude 4-Layer Memory System!**
