# Claude 4-Layer Memory System - Architecture Analysis

**Date:** 2026-04-18  
**Status:** Complete

---

## System Components

### Core Scripts

#### L4 SEMANTIC Layer
- **l4_semantic_global.py** (22KB) - Main semantic search engine
  - Auto-discovery of projects
  - Whitelist filtering
  - Cleanup mechanism
  - Multi-collection support
  - Multilingual embeddings

#### Memory Management
- **stop-handoff-dual-level.py** (8KB) - Session summary writer
- **rotate_hot_memory.py** (5KB) - HOT memory rotation (24h window)
- **rotate_to_cold.py** - WARM to COLD archival
- **memory_health_check.py** (10KB) - System health monitoring

#### Semantic Search (Legacy)
- **semantic_indexer.py** (10KB) - Old indexer
- **semantic_search.py** (3KB) - Old search interface

#### Setup & Utilities
- **setup_l4_project.py** (9KB) - Project initialization
- **precompact-flush-l4.py** (2KB) - Pre-compact L4 flush

### Batch Scripts (Windows)

#### L4 Commands
- **l4_index.bat** - Index current project
- **l4_index_all.bat** - Index all projects
- **l4_search.bat** - Search in current project
- **l4_search_all.bat** - Search everywhere
- **l4_search_global.bat** - Search global memory
- **l4_stats.bat** - Show statistics

#### Setup
- **setup_l4.bat** - L4 setup wizard
- **setup_l4_cron.bat** - Schedule L4 tasks

#### Health Check
- **run_health_check.bat** - Manual health check
- **setup_health_check_task.bat** - Schedule health checks

### Shell Scripts (Linux/Mac)

- **semantic_search.sh** - Search interface
- **session-start.sh** - Session initialization

### Documentation Files

#### Main Docs
- **DUAL_LEVEL_MEMORY_SYSTEM.md** (13KB) - Architecture overview
- **L4_SEMANTIC_GUIDE.md** (5KB) - L4 usage guide
- **GLOBAL_CONTEXT_SYSTEM.md** (8KB) - Context management
- **ROTATION_SETUP.md** (8KB) - Rotation configuration

#### Setup Guides
- **L4_INTEGRATION_COMPLETE.md** (5KB) - Integration guide
- **L4_UNIVERSAL_SETUP_COMPLETE.md** (7KB) - Universal setup
- **HOOK_INSTALLED.md** (3KB) - Hook installation
- **MULTILINGUAL_MIGRATION.md** (5KB) - Multilingual setup

#### Reference
- **PRECOMPACT_FLUSH_HOOK.md** (7KB) - Flush hook docs
- **COMPARISON_AI_DY_BOT.md** (10KB) - Comparison with other systems

### Memory Structure

#### Global Memory (~/.claude/memory/)
```
memory/
├── MEMORY.md                    # Index
├── handoff.md                   # HOT (24h)
├── decisions.md                 # WARM (14d)
├── archive/                     # COLD (permanent)
├── user_*.md                    # User profiles
├── feedback_*.md                # Feedback memories
├── project_*.md                 # Project overviews
├── reference_*.md               # Reference materials
└── outputs/                     # Generated reports
```

#### Project Memory (~/.claude/projects/<project>/memory/)
```
memory/
├── MEMORY.md                    # Project index
├── handoff.md                   # Project HOT
├── decisions.md                 # Project WARM
├── archive/                     # Project COLD
├── semantic_db/                 # L4 vector DB
├── feedback_*.md                # Project feedback
└── outputs/                     # Project reports
```

### Dependencies

#### Python Packages
- **chromadb** - Vector database
- **sentence-transformers** - Embeddings model
- **paraphrase-multilingual-MiniLM-L12-v2** - Multilingual model

#### System Requirements
- Python 3.7+
- 500MB disk space (for embeddings model)
- Windows/Linux/Mac support

---

## Architecture Layers

### Layer 1: HOT Memory (24 hours)
- **File:** handoff.md
- **Rotation:** Automatic via rotate_hot_memory.py
- **Purpose:** Recent events, quick context recovery

### Layer 2: WARM Memory (14 days)
- **File:** decisions.md
- **Rotation:** Manual or scheduled
- **Purpose:** Important decisions, architectural choices

### Layer 3: COLD Memory (permanent)
- **Directory:** archive/
- **Rotation:** From WARM after 14 days
- **Purpose:** Long-term storage, historical reference

### Layer 4: SEMANTIC Memory (indexed)
- **Directory:** semantic_db/
- **Technology:** ChromaDB + sentence-transformers
- **Purpose:** Semantic search across all layers

---

## Key Features

### 1. Dual-Level System
- Global memory (cross-project knowledge)
- Project memory (project-specific details)

### 2. Auto-Discovery
- Parses GLOBAL_PROJECTS.md
- Fallback: structure-based detection
- Filters system directories

### 3. Whitelist Protection
- Only real projects indexed
- System directories excluded
- Cleanup mechanism for junk

### 4. Multilingual Support
- Russian + English + 50+ languages
- Semantic search works across languages

### 5. Health Monitoring
- Automatic rotation checks
- Memory size monitoring
- Corruption detection

---

## Integration Points

### Hooks
- **SessionStart** - Load context, check rotation
- **Stop** - Write session summary
- **PreCompact** - Flush L4 before compaction

### Commands
- `/remember` - Save to memory
- `/recall` - Search memory
- Custom skills integration

---

## Files to Package

### Essential Scripts (11 files)
1. l4_semantic_global.py
2. stop-handoff-dual-level.py
3. rotate_hot_memory.py
4. memory_health_check.py
5. setup_l4_project.py
6. precompact-flush-l4.py
7. l4_*.bat (6 files)

### Documentation (8 files)
1. DUAL_LEVEL_MEMORY_SYSTEM.md
2. L4_SEMANTIC_GUIDE.md
3. GLOBAL_CONTEXT_SYSTEM.md
4. ROTATION_SETUP.md
5. L4_INTEGRATION_COMPLETE.md
6. MULTILINGUAL_MIGRATION.md
7. PRECOMPACT_FLUSH_HOOK.md
8. README.md (to create)

### Configuration Templates (3 files)
1. GLOBAL_PROJECTS.md.template
2. settings.json.template
3. .env.template

---

## Total Package Size
- Scripts: ~100KB
- Documentation: ~80KB
- Model (downloaded separately): ~500MB
- Total (without model): ~200KB

---

**Next Steps:**
1. Create repository structure
2. Generalize code (remove personal data)
3. Write installation scripts
4. Create comprehensive documentation
5. Add CREDITS.md
6. Test on clean system
