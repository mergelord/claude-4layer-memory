# Usage Guide

Complete guide to using Claude 4-Layer Memory System.

---

## Table of Contents

- [Quick Start](#quick-start)
- [Basic Commands](#basic-commands)
- [Indexing](#indexing)
- [Searching](#searching)
- [Managing Projects](#managing-projects)
- [Memory Layers](#memory-layers)
- [Advanced Usage](#advanced-usage)
- [Best Practices](#best-practices)

---

## Quick Start

### 1. Add Your First Project

Edit `~/.claude/GLOBAL_PROJECTS.md`:

```markdown
### My Project
**Path:** `/home/user/projects/my-app`
**Memory:** `~/.claude/projects/home-user-projects-my-app/memory/`
**Status:** ✅ Active
```

### 2. Index the Project

**Windows:**
```cmd
l4_index_all.bat
```

**Linux/macOS:**
```bash
l4_index_all.sh
```

### 3. Search

**Windows:**
```cmd
l4_search_all.bat "how to handle errors"
```

**Linux/macOS:**
```bash
l4_search_all.sh "how to handle errors"
```

---

## Basic Commands

### Indexing Commands

| Command | Description | Example |
|---------|-------------|---------|
| `l4_index_all` | Index all projects | `l4_index_all.bat` |
| `python l4_semantic_global.py index-global` | Index global memory only | - |
| `python l4_semantic_global.py index-project <path>` | Index specific project | - |

### Search Commands

| Command | Description | Example |
|---------|-------------|---------|
| `l4_search_all "query"` | Search everywhere | `l4_search_all.bat "API design"` |
| `l4_search_global "query"` | Search global memory | `l4_search_global.bat "coding style"` |
| `python l4_semantic_global.py search-project <name> "query"` | Search specific project | - |

### Utility Commands

| Command | Description | Example |
|---------|-------------|---------|
| `l4_stats` | Show statistics | `l4_stats.bat` |
| `l4_cleanup --dry-run` | Preview cleanup | `l4_cleanup.bat --dry-run` |
| `l4_cleanup` | Clean junk collections | `l4_cleanup.bat` |

---

## Indexing

### Index All Projects

Indexes global memory + all projects from GLOBAL_PROJECTS.md:

**Windows:**
```cmd
l4_index_all.bat
```

**Output:**
```
[AUTO] Found project in GLOBAL_PROJECTS.md: my-project
[AUTO] Using 1 projects from GLOBAL_PROJECTS.md
[INFO] Indexing global memory: C:\Users\user\.claude\memory
[OK] Indexed 9 files from global memory
[INFO] Indexing project: my_project
[OK] Indexed 15 files from my_project
```

### Index Specific Project

```bash
python ~/.claude/hooks/l4_semantic_global.py index-project /path/to/project
```

### When to Reindex

Reindex when:
- ✅ Added new project to GLOBAL_PROJECTS.md
- ✅ Made significant changes to memory files
- ✅ Added new documentation
- ✅ After cleanup

**Tip:** Indexing is fast (usually <30 seconds), so reindex often!

---

## Searching

### Search Across All Projects

Find information from any project:

```bash
l4_search_all.sh "database connection pooling"
```

**Output:**
```
[SEARCH ALL] 'database connection pooling'

[1] [project-A] decisions.md (distance: 12.345)
    We decided to use connection pooling with max_connections=20...

[2] [project-B] feedback.md (distance: 13.456)
    Connection pooling improved performance by 40%...

[3] [global] reference_resources.md (distance: 14.567)
    Best practices for database connection management...
```

### Search Global Memory Only

Find cross-project knowledge:

```bash
l4_search_global.sh "error handling patterns"
```

**Use cases:**
- Coding standards
- Development principles
- User preferences
- Global decisions

### Search Specific Project

```bash
python l4_semantic_global.py search-project my-project "authentication"
```

### Understanding Search Results

**Distance:** Lower = more relevant
- `< 10` - Highly relevant
- `10-15` - Relevant
- `15-20` - Somewhat relevant
- `> 20` - Less relevant

**Source:** Where the result came from
- `[global]` - Global memory
- `[project-name]` - Specific project

---

## Managing Projects

### Adding New Project

1. **Create project memory directory:**

```bash
mkdir -p ~/.claude/projects/my-new-project/memory
```

2. **Add to GLOBAL_PROJECTS.md:**

```markdown
### My New Project
**Path:** `/home/user/projects/new-project`
**Memory:** `~/.claude/projects/my-new-project/memory/`
**Status:** ✅ Active

**Description:**
Brief description of the project.
```

3. **Initialize memory files:**

```bash
cp templates/MEMORY.md.template ~/.claude/projects/my-new-project/memory/MEMORY.md
cp templates/handoff.md.template ~/.claude/projects/my-new-project/memory/handoff.md
cp templates/decisions.md.template ~/.claude/projects/my-new-project/memory/decisions.md
```

4. **Index:**

```bash
l4_index_all.sh
```

### Removing Project

1. **Remove from GLOBAL_PROJECTS.md**
2. **Cleanup old collection:**

```bash
l4_cleanup.sh --dry-run  # Preview
l4_cleanup.sh            # Execute
```

3. **Optionally delete memory directory:**

```bash
rm -rf ~/.claude/projects/old-project
```

---

## Memory Layers

### Layer 1: HOT (24 hours)

**File:** `handoff.md`

**Purpose:** Recent events, quick context recovery

**Example:**
```markdown
### 2026-04-18 14:30 - Fixed Authentication Bug

**What happened:**
- JWT token validation was failing for expired tokens

**Solution:**
- Added proper expiry check in middleware

**Next steps:**
- Add tests for token expiration
```

**When to use:**
- Session summaries
- Recent changes
- Quick notes

### Layer 2: WARM (14 days)

**File:** `decisions.md`

**Purpose:** Important decisions, architectural choices

**Example:**
```markdown
### Database Choice: PostgreSQL

**Decision:** Use PostgreSQL instead of MySQL
**Reason:** Better JSON support, ACID compliance
**Date:** 2026-04-15

**Why:**
- Project requires complex queries
- JSON columns needed for flexible schema

**How to apply:**
- All new tables in PostgreSQL
- Use pg_dump for backups
```

**When to use:**
- Architectural decisions
- Technology choices
- Important patterns

### Layer 3: COLD (permanent)

**Directory:** `archive/`

**Purpose:** Long-term storage, historical reference

**Example:**
```
archive/
├── 2026-03/
│   ├── decisions_2026-03.md
│   └── handoff_2026-03.md
└── 2026-02/
    └── decisions_2026-02.md
```

**When to use:**
- Archived decisions
- Historical context
- Old project documentation

### Layer 4: SEMANTIC (indexed)

**Directory:** `semantic_db/`

**Purpose:** Fast semantic search across all layers

**Features:**
- Multilingual search
- Finds by meaning, not keywords
- Cross-project search

---

## Advanced Usage

### Custom Search Queries

**Find similar concepts:**
```bash
l4_search_all.sh "async programming patterns"
# Also finds: "asynchronous code", "concurrent execution", etc.
```

**Multilingual search:**
```bash
l4_search_all.sh "обработка ошибок"  # Russian
# Finds: "error handling", "exception management", etc.
```

### Cleanup Strategies

**Preview what will be deleted:**
```bash
l4_cleanup.sh --dry-run
```

**Output:**
```
[CLEANUP] L4 SEMANTIC Collections
   Mode: DRY RUN

   Keep (2):
      ✓ memory_global (63 chunks)
      ✓ memory_my_project (199 chunks)

   Delete (1):
      ✗ memory_old_temp_project (50 chunks) - not in whitelist
```

**Execute cleanup:**
```bash
l4_cleanup.sh
```

### Statistics and Monitoring

**View detailed statistics:**
```bash
l4_stats.sh
```

**Output:**
```
[STATS] L4 SEMANTIC Global Statistics:
   DB path: /home/user/.claude/semantic_db_global
   Total collections: 3

   Collections:
      memory_global: 63 chunks
         Global memory - knowledge applicable to all projects
      memory_project_a: 227 chunks
         Project memory: project_a
      memory_project_b: 199 chunks
         Project memory: project_b
```

### Batch Operations

**Index multiple projects:**
```bash
for project in project1 project2 project3; do
    python l4_semantic_global.py index-project "/path/to/$project"
done
```

**Search multiple queries:**
```bash
queries=("error handling" "database design" "API patterns")
for query in "${queries[@]}"; do
    echo "=== Searching: $query ==="
    l4_search_all.sh "$query"
done
```

---

## Best Practices

### 1. Regular Indexing

**Recommended schedule:**
- After significant changes: Immediate
- Daily work: End of day
- Weekly: Full reindex

**Automation (Linux/Mac):**
```bash
# Add to crontab
0 18 * * * cd ~/.claude/hooks && ./l4_index_all.sh
```

### 2. Memory Organization

**Global memory:**
- ✅ Coding standards
- ✅ Development principles
- ✅ User preferences
- ❌ Project-specific code
- ❌ Temporary notes

**Project memory:**
- ✅ Project decisions
- ✅ Implementation details
- ✅ Project history
- ❌ General principles
- ❌ Cross-project patterns

### 3. Search Strategies

**Start broad, then narrow:**
```bash
# 1. Search everywhere
l4_search_all.sh "authentication"

# 2. If too many results, search specific project
python l4_semantic_global.py search-project my-project "authentication"

# 3. Or search global only
l4_search_global.sh "authentication best practices"
```

**Use semantic search:**
```bash
# Instead of exact keywords
l4_search_all.sh "JWT token validation"

# Try semantic concepts
l4_search_all.sh "secure user authentication"
```

### 4. Cleanup Regularly

**Monthly cleanup:**
```bash
# Check what can be cleaned
l4_cleanup.sh --dry-run

# Clean if needed
l4_cleanup.sh
```

### 5. GLOBAL_PROJECTS.md Maintenance

**Keep it updated:**
- ✅ Add new projects immediately
- ✅ Mark inactive projects
- ✅ Remove deleted projects
- ✅ Update descriptions

**Example:**
```markdown
### Active Project
**Status:** ✅ Active

### Archived Project
**Status:** 📦 Archived

### Deprecated Project
**Status:** ⚠️ Deprecated
```

---

## Common Workflows

### Workflow 1: Starting New Project

```bash
# 1. Create memory directory
mkdir -p ~/.claude/projects/new-project/memory

# 2. Copy templates
cp templates/*.template ~/.claude/projects/new-project/memory/

# 3. Add to GLOBAL_PROJECTS.md
vim ~/.claude/GLOBAL_PROJECTS.md

# 4. Index
l4_index_all.sh

# 5. Verify
l4_stats.sh
```

### Workflow 2: Finding Past Solutions

```bash
# 1. Search broadly
l4_search_all.sh "database migration"

# 2. Review results
# 3. If found in another project, adapt solution
# 4. Document in current project
```

### Workflow 3: Daily Maintenance

```bash
# Morning: Check what's indexed
l4_stats.sh

# During day: Work on projects
# (Memory files updated automatically by Claude)

# Evening: Reindex
l4_index_all.sh

# Weekly: Cleanup
l4_cleanup.sh --dry-run
```

---

## Troubleshooting

### No results found

**Problem:** Search returns no results

**Solutions:**
1. Check if project is indexed: `l4_stats.sh`
2. Reindex: `l4_index_all.sh`
3. Try different search terms
4. Check GLOBAL_PROJECTS.md

### Slow search

**Problem:** Search takes too long

**Solutions:**
1. Cleanup old collections: `l4_cleanup.sh`
2. Reduce number of indexed projects
3. Check system resources

### Wrong results

**Problem:** Search returns irrelevant results

**Solutions:**
1. Use more specific queries
2. Search in specific project instead of all
3. Check if memory files contain relevant content

---

## Next Steps

- **Configuration:** See [CONFIGURATION.md](CONFIGURATION.md)
- **Architecture:** See [ARCHITECTURE.md](../architecture/ARCHITECTURE.md)
- **Examples:** See [examples/](../../examples/)

---

**Happy searching with Claude 4-Layer Memory System!**
