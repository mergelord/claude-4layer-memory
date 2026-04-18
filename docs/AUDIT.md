# Pre-Installation Audit

**Always run the audit before installing!**

---

## What is the Audit?

The pre-installation audit analyzes your current Claude Code setup and provides a detailed report before making any changes.

**The audit checks:**
- ✅ Claude Code installation
- ✅ Existing memory structure
- ✅ Project directories
- ✅ Semantic database
- ✅ Python dependencies
- ✅ Disk space

**The audit does NOT:**
- ❌ Modify any files
- ❌ Install anything
- ❌ Delete data

---

## Running the Audit

### Windows

```cmd
audit.bat
```

### Linux / macOS

```bash
chmod +x audit.sh
./audit.sh
```

### Direct Python

```bash
python audit.py
```

---

## Understanding the Report

### Section 1: Claude Code Installation

```
## Claude Code Installation
--------------------------------------------------
✓ Claude Code directory found: /home/user/.claude
✓ Hooks directory exists (15 files)
```

**What it means:**
- Claude Code is properly installed
- Hooks directory exists with 15 existing hooks

### Section 2: Current Memory Structure

```
## Current Memory Structure
--------------------------------------------------
✓ Memory directory exists: /home/user/.claude/memory
✓ MEMORY.md exists (1234 bytes) - Memory index
✓ handoff.md exists (5678 bytes) - HOT layer (24h)
✓ decisions.md exists (9012 bytes) - WARM layer (14d)
✓ Archive directory exists (25 files)
ℹ Total memory files: 30
ℹ Total memory size: 150.5 KB
```

**What it means:**
- You already have a memory system
- Your existing data will be preserved
- Installation will add new features without modifying existing files

### Section 3: Existing Projects

```
## Existing Projects
--------------------------------------------------
✓ Found 3 project directories
✓   my-project-1 (15 memory files)
✓   my-project-2 (20 memory files)
⚠   temp-project (no memory directory)
```

**What it means:**
- 3 projects found
- 2 have memory directories (will be indexed)
- 1 has no memory (will be skipped)

### Section 4: Project Registry

```
## Project Registry
--------------------------------------------------
✓ GLOBAL_PROJECTS.md exists (2345 bytes)
ℹ Contains 2 project entries
```

**What it means:**
- You already have GLOBAL_PROJECTS.md
- It will not be overwritten
- You can add more projects after installation

### Section 5: Semantic Search

```
## Semantic Search (L4 Layer)
--------------------------------------------------
✓ Semantic database exists (125.5 MB)
✓ ChromaDB found (120.3 KB)
```

**What it means:**
- You already have L4 SEMANTIC installed
- Installation will upgrade it
- Existing index will be preserved

### Section 6: Python Dependencies

```
## Python Dependencies
--------------------------------------------------
✓ Python 3.10.5 (>= 3.7 required)
✓ chromadb installed - Vector database for semantic search
⚠ sentence_transformers not installed - Multilingual embeddings
  Install with: pip install sentence_transformers
```

**What it means:**
- Python version is OK
- chromadb is installed
- sentence_transformers needs to be installed

### Section 7: Disk Space

```
## Disk Space
--------------------------------------------------
ℹ Free space: 15.3 GB
✓ Sufficient disk space (15.3 GB free)
```

**What it means:**
- Plenty of space for installation
- Embeddings model requires ~500MB

---

## Recommendations

### No Issues (Green Light)

```
## Recommendations
--------------------------------------------------
✓ No issues found! Safe to proceed with installation.
```

**Action:** Proceed with installation

### Warnings Only (Yellow Light)

```
## Recommendations
--------------------------------------------------

Warnings:
  ⚠ sentence_transformers not installed - Multilingual embeddings
  ⚠ Less than 1 GB free (recommended: 1GB+)

These warnings can be ignored, but review them carefully.
```

**Action:** Review warnings, then proceed if acceptable

### Critical Issues (Red Light)

```
## Recommendations
--------------------------------------------------

Critical Issues:
  ✗ Claude Code directory not found: /home/user/.claude
  ✗ Python 2.7.18 (3.7+ required)

Please resolve these issues before installing.
```

**Action:** Fix issues, then run audit again

---

## Installation Readiness Summary

```
Installation Readiness Summary
======================================================================

Current State:
  Claude Code: Installed
  Memory System: Exists
  Projects: 3 found
  Semantic DB: Exists

Statistics:
  Total memory files: 30
  Memory size: 150.5 KB
  Projects with memory: 2
  Archive files: 25

Installation Impact:
  ⚠ Existing memory will be preserved
  ✓ New features will be added
  ✓ Existing data will not be modified

What will be installed:
  • L4 SEMANTIC search engine
  • Auto-discovery system
  • Cleanup utilities
  • Cross-platform scripts
  • Configuration templates

What will NOT be changed:
  • Existing memory files
  • Project directories
  • GLOBAL_PROJECTS.md (if exists)
  • Archive data
```

---

## Audit Report File

The audit saves a detailed JSON report:

**File:** `pre_install_audit_report.json`

**Contents:**
```json
{
  "timestamp": "2026-04-18T23:59:00",
  "claude_dir": "/home/user/.claude",
  "stats": {
    "existing_hooks": 15,
    "has_memory": true,
    "total_memory_files": 30,
    "total_memory_size": 154112,
    "project_count": 3,
    "projects_with_memory": 2,
    "archive_files": 25,
    "has_semantic_db": true,
    "free_space_gb": 15.3
  },
  "issues": [],
  "warnings": [
    "sentence_transformers not installed"
  ],
  "info": [...]
}
```

**Use this report to:**
- Share with support if you have issues
- Track changes over time
- Document your setup

---

## Common Scenarios

### Scenario 1: Fresh Installation

```
Current State:
  Claude Code: Installed
  Memory System: Not Found
  Projects: 0 found
  Semantic DB: Not Found

Installation Impact:
  ✓ Fresh installation
  ✓ No existing data to preserve
```

**Action:** Proceed with installation

### Scenario 2: Existing Memory System

```
Current State:
  Claude Code: Installed
  Memory System: Exists
  Projects: 5 found
  Semantic DB: Not Found

Installation Impact:
  ⚠ Existing memory will be preserved
  ✓ New features will be added
  ✓ Existing data will not be modified
```

**Action:** Proceed with installation (your data is safe)

### Scenario 3: Already Installed

```
Current State:
  Claude Code: Installed
  Memory System: Exists
  Projects: 3 found
  Semantic DB: Exists

Installation Impact:
  ⚠ Existing memory will be preserved
  ✓ New features will be added
  ✓ Existing data will not be modified
```

**Action:** This is an upgrade, proceed to update

### Scenario 4: Missing Dependencies

```
Critical Issues:
  ✗ Python 2.7.18 (3.7+ required)

Warnings:
  ⚠ chromadb not installed
  ⚠ sentence_transformers not installed
```

**Action:**
1. Upgrade Python to 3.7+
2. Install dependencies: `pip install chromadb sentence-transformers`
3. Run audit again

---

## Next Steps After Audit

### If Audit Passes

```bash
# Windows
install.bat

# Linux/Mac
./install.sh
```

### If Audit Fails

1. Review critical issues
2. Fix each issue
3. Run audit again
4. Proceed when audit passes

---

## FAQ

**Q: Will the audit modify my files?**  
A: No, the audit only reads files and generates a report.

**Q: How long does the audit take?**  
A: Usually 5-10 seconds.

**Q: Can I skip the audit?**  
A: Not recommended. The audit prevents installation issues.

**Q: What if I have warnings but no errors?**  
A: You can proceed, but review warnings carefully.

**Q: Can I run the audit multiple times?**  
A: Yes, run it as many times as you want.

---

## Support

If the audit finds issues you can't resolve:

- **Issues:** https://github.com/yourusername/claude-4layer-memory/issues
- **Discussions:** https://github.com/yourusername/claude-4layer-memory/discussions

---

**Always audit before installing!**
