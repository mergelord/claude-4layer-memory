# Changelog

All notable changes to claude-4layer-memory will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.2.0] - 2026-04-22

### Added

#### Linguistic Triggers for Semantic Search
- **30+ new trigger patterns** inspired by Claude Opus 4.7 system prompt
  - Possessive pronouns: "my project", "our code", "my system"
  - Definite articles: "the script", "the bug", "the solution"
  - Past tense references: "you recommended", "we discussed", "you helped"
  - Russian equivalents: "ты рекомендовал", "мы обсуждали", "моего проекта"
- **Automatic context retrieval** on natural linguistic signals
- **Trigger logging** to `~/.claude/hooks/semantic_search.log` for debugging
- Bilingual support (English + Russian)

### Changed
- `semantic_search.py` now detects contextual references automatically
- Improved natural language understanding for memory retrieval

## [1.1.0] - 2026-04-19

### Added

#### Memory Lint Quick Mode
- **`--quick` flag** for fast validation during SessionStart
  - Only checks critical errors (ghost links)
  - Completes in <1 second
  - Suitable for automatic hooks
  - Exit code 1 only on critical errors

#### New Templates
- `memory_lint_quick.bat` - Quick check for global memory
- `memory_lint_full.bat` - Full check (Layer 1 + Layer 2)
- `memory_lint_project.bat` - Project memory check with optional --quick

#### SessionStart Integration
- Memory Lint can now run automatically on session start
- Quick mode prevents startup delays
- Provides immediate feedback on memory integrity

### Changed

#### Memory Lint Core
- `MemoryLint.__init__()` now accepts `quick_mode: bool = False` parameter
- `run_layer1()` adapts behavior based on quick_mode:
  - Quick mode: only ghost links check
  - Normal mode: all Layer 1 checks
- Layer 2 automatically skipped in quick mode
- Improved summary output for quick mode

### Technical Details

**Modified Files:**
- `scripts/memory_lint.py` - Added quick_mode support
  - Line 41: Updated constructor signature
  - Line 321-345: Modified run_layer1() for quick mode
  - Line 594-598: Added --quick argument
  - Line 608: Pass quick_mode to constructor
  - Line 613: Skip Layer 2 in quick mode

**New Files:**
- `templates/memory_lint_quick.bat`
- `templates/memory_lint_full.bat`
- `templates/memory_lint_project.bat`

### Usage Examples

**Quick check (SessionStart hook):**
```bash
python memory_lint.py --layer 1 --quick
```

**Full Layer 1 check:**
```bash
python memory_lint.py --layer 1
```

**Full check with report:**
```bash
python memory_lint.py --layer all --report report.json
```

**Project memory check:**
```bash
cd ~/.claude/projects/<project>/memory
python ~/.claude/hooks/memory_lint.py . --layer 1 --quick
```

### Integration with settings.json

Add to SessionStart hook:
```json
{
  "hooks": {
    "SessionStart": [
      {
        "type": "command",
        "command": "python C:/Users/USERNAME/.claude/hooks/memory_lint.py --layer 1 --quick"
      }
    ]
  }
}
```

### Performance

- **Quick mode:** ~0.5-1s (ghost links only)
- **Layer 1 full:** ~2-5s (all deterministic checks)
- **Layer 1 + 2:** ~10-30s (includes semantic analysis)

### Backward Compatibility

All existing functionality preserved:
- Default behavior unchanged (no --quick = full checks)
- All Layer 1 and Layer 2 checks work as before
- Exit codes remain the same

## [1.0.0] - 2026-04-18

### Added
- Initial release
- Layer 1: Deterministic checks
  - Ghost links detection
  - Orphan files detection
  - Duplicate titles detection
  - HOT memory age check (24h)
  - WARM memory age check (14d)
  - File size check (>100KB)
- Layer 2: Semantic checks
  - Contradiction detection (structure)
  - Outdated claims detection (>30d)
  - Consistency verification
  - Completeness analysis (TODO/FIXME)
- Windows and Linux support
- JSON report generation
- Colored terminal output

### Credits
- Inspired by llm-atomic-wiki's lint approach
- Part of claude-4layer-memory system

---

## Roadmap

### [1.2.0] - Planned
- [ ] Layer 2: Claude API integration for contradiction detection
- [ ] Auto-fix mode (--fix flag)
- [ ] L4 SEMANTIC integration
- [ ] Web dashboard for reports

### [2.0.0] - Planned
- [ ] Quality checks for Why:/How to apply: sections
- [ ] Automatic rotation of outdated entries
- [ ] Git hooks integration (pre-commit)
- [ ] Multi-project analysis (cross-project links)
- [ ] CI/CD templates

---

[1.1.0]: https://github.com/mergelord/claude-4layer-memory/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/mergelord/claude-4layer-memory/releases/tag/v1.0.0
