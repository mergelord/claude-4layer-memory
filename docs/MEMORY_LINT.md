# Memory Lint System

**Two-layer validation system for memory health checks**

Inspired by [llm-atomic-wiki](https://github.com/art20217/llm-atomic-wiki)'s lint approach.

---

## Overview

Memory Lint validates your memory structure and content in two layers:

**Layer 1: Deterministic Checks** (implemented)
- Ghost links detection
- Orphan files detection
- Duplicate content detection
- HOT memory age validation (24h window)
- WARM memory age validation (14d window)
- File size checks

**Layer 2: Semantic Checks** (planned)
- Contradiction detection
- Outdated claims detection
- Consistency verification
- Completeness analysis

---

## Usage

### Check Global Memory

**Windows:**
```cmd
cd %USERPROFILE%\.claude\hooks
memory_lint.bat
```

**Linux/Mac:**
```bash
cd ~/.claude/hooks
./memory_lint.sh
```

### Check Project Memory

**Windows:**
```cmd
memory_lint_project.bat C:\path\to\project
```

**Linux/Mac:**
```bash
./memory_lint_project.sh /path/to/project
```

### Direct Python Usage

```bash
# Global memory
python memory_lint.py ~/.claude/memory

# Project memory
python memory_lint.py ~/.claude/projects/C--BAT-my-project/memory

# Save report to JSON
python memory_lint.py ~/.claude/memory --report lint_report.json

# Run only Layer 1
python memory_lint.py ~/.claude/memory --layer 1
```

---

## Layer 1 Checks

### 1. Ghost Links Detection

**What it checks:**
- Markdown links `[text](file.md)` pointing to non-existent files

**Example output:**
```
[ERROR] MEMORY.md: 4 ghost link(s)
    -> reference_edgelab.md
    -> feedback_memory_usage.md
```

**How to fix:**
- Create missing files
- Remove broken links
- Update links to correct paths

### 2. Orphan Files Detection

**What it checks:**
- Files not linked from anywhere (except index files)

**Example output:**
```
[WARN] Orphan file: independence_from_ai.md
[WARN] Orphan file: outputs\l4_cleanup_2026-04-18.md
```

**How to fix:**
- Add links to orphan files in MEMORY.md
- Archive or delete unused files

### 3. Duplicate Detection

**What it checks:**
- Multiple files with same title (first heading)

**Example output:**
```
[WARN] Duplicate title: 'HOT Memory 24h Window'
    -> feedback_hot_memory.md
    -> reference_hot_memory.md
```

**How to fix:**
- Merge duplicate files
- Rename to make titles unique

### 4. HOT Memory Age Check

**What it checks:**
- Entries in `handoff.md` older than 24 hours

**Example output:**
```
[WARN] HOT entry older than 24h: 2026-04-17 10:30 (38h old)
[INFO] Consider rotating old entries to WARM layer
```

**How to fix:**
- Move old entries to `decisions.md` (WARM layer)
- Archive very old entries

### 5. WARM Memory Age Check

**What it checks:**
- Entries in `decisions.md` older than 14 days

**Example output:**
```
[WARN] WARM entry older than 14d: 2026-04-01 (18d old)
[INFO] Consider archiving old entries to COLD layer
```

**How to fix:**
- Move old entries to `archive/` directory
- Keep only recent decisions in WARM layer

### 6. File Size Check

**What it checks:**
- Files larger than 100KB

**Example output:**
```
[WARN] Large file: decisions.md (150.5 KB)
[INFO] Consider splitting large files into smaller chunks
```

**How to fix:**
- Split large files by topic
- Archive old content
- Move detailed content to separate files

---

## Exit Codes

- `0` - No errors found (warnings are OK)
- `1` - Errors found (ghost links, etc.)

---

## Integration with CI/CD

Add to your pre-commit hook:

```bash
#!/bin/bash
# .git/hooks/pre-commit

python ~/.claude/hooks/memory_lint.py ~/.claude/memory --layer 1

if [ $? -ne 0 ]; then
    echo "Memory lint failed! Fix errors before committing."
    exit 1
fi
```

---

## Automated Checks

Run lint automatically:

**Daily check (cron):**
```bash
# Add to crontab
0 9 * * * python ~/.claude/hooks/memory_lint.py ~/.claude/memory --report ~/memory_lint_$(date +\%Y\%m\%d).json
```

**Weekly cleanup:**
```bash
# Check all projects
for project in ~/.claude/projects/*/memory; do
    python ~/.claude/hooks/memory_lint.py "$project"
done
```

---

## Layer 2: Semantic Checks (Planned)

Future LLM-based checks:

### Contradiction Detection
```
[ERROR] Contradiction found:
  decisions.md:15 - "We use SimConnect for all autopilot commands"
  decisions.md:42 - "PMDG requires WASM, not SimConnect"
```

### Outdated Claims Detection
```
[WARN] Potentially outdated:
  decisions.md:23 - "MobiFlight WASM not yet tested" (30 days old)
  handoff.md:5 - "WASM integration completed" (2 days old)
```

### Consistency Verification
```
[WARN] Inconsistent terminology:
  - "auto-pilot" (3 occurrences)
  - "autopilot" (15 occurrences)
  - "AP" (8 occurrences)
  Suggest: standardize to "autopilot"
```

### Completeness Analysis
```
[INFO] Missing documentation:
  - Decision "Why we chose vJoy" has no rationale
  - Pattern "WASM fallback" has no examples
```

---

## Best Practices

1. **Run lint before committing**
   - Catch issues early
   - Keep memory clean

2. **Fix errors immediately**
   - Ghost links break navigation
   - Orphans waste space

3. **Review warnings regularly**
   - Rotate old HOT entries weekly
   - Archive old WARM entries monthly

4. **Use reports for tracking**
   - Save JSON reports
   - Track improvements over time

5. **Automate checks**
   - Add to CI/CD pipeline
   - Schedule regular audits

---

## Troubleshooting

**Q: Lint reports ghost links but files exist**
A: Check file paths are relative to the file containing the link

**Q: Too many orphan warnings**
A: Exclude output files from checks (they're meant to be orphans)

**Q: HOT memory always shows warnings**
A: Set up automatic rotation with stop hooks

**Q: Large file warnings for archive**
A: Archive files can be large, warnings are informational

---

## Configuration

Future: `memory_lint.json` config file

```json
{
  "layer1": {
    "ghost_links": true,
    "orphans": true,
    "duplicates": true,
    "hot_age_hours": 24,
    "warm_age_days": 14,
    "max_file_size_kb": 100
  },
  "layer2": {
    "contradictions": true,
    "outdated_claims": true,
    "consistency": true,
    "completeness": false
  },
  "exclude_patterns": [
    "outputs/*.md",
    "archive/*.md"
  ]
}
```

---

## Credits

Inspired by:
- [llm-atomic-wiki](https://github.com/art20217/llm-atomic-wiki) - Two-layer lint concept
- [qwwiwi/second-brain](https://github.com/qwwiwi/second-brain) - Memory health checks

---

## See Also

- [USAGE.md](guides/USAGE.md) - Memory system usage
- [CONFIGURATION.md](guides/CONFIGURATION.md) - Memory configuration
- [AUDIT.md](AUDIT.md) - Pre-installation audit
