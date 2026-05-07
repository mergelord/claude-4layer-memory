# EncodingGate - Encoding Validation and Cleanup

**Version:** 1.3.1  
**Module:** `scripts/memory_lint_helpers.py`  
**Status:** Production

---

## Overview

`EncodingGate` is a comprehensive encoding validation and cleanup system that prevents and repairs UTF-8 corruption in memory files. It addresses the common Windows issue where subprocess output (cp1251/cp866) gets concatenated into UTF-8 files, producing mojibake that causes "the agent forgets what we did" symptoms.

---

## Problem Statement

### The Mojibake Issue

On Windows, subprocess output (git log, PowerShell, etc.) defaults to cp1251 (Cyrillic) or cp866 codepage. When hooks naively concatenate these bytes into UTF-8 memory files:

```python
# ❌ WRONG - produces mojibake
output = subprocess.check_output(['git', 'log'])
with open('handoff.md', 'ab') as f:
    f.write(output)  # cp1251 bytes written as UTF-8
```

The result is **mojibake** - corrupted text that looks like:
- `РџСЂРѕРµРєС‚` instead of `Проект`
- `РёСЃС‚РѕСЂРёСЏ` instead of `история`

### User-Visible Symptoms

1. Claude "forgets" previous session context
2. Memory files contain garbled Russian/Cyrillic text
3. Semantic search returns irrelevant results
4. Memory lint reports encoding errors

---

## API Reference

### Validation Methods (for hooks)

#### `assert_clean(text, *, source="<unknown>")`

Validates that text is safe to write to UTF-8 memory files.

**Raises:** `EncodingError` if text contains:
- Unicode replacement character (U+FFFD)
- cp1251-as-utf8 mojibake patterns

**Usage:**
```python
from memory_lint_helpers import EncodingGate

# In a hook writing to memory
text = subprocess.check_output(['git', 'log']).decode('utf-8')
EncodingGate.assert_clean(text, source="git log subprocess")
```

---

#### `assert_clean_bytes(data, *, source="<unknown>")`

Decodes bytes as UTF-8 and validates the result.

**Returns:** Successfully decoded UTF-8 string  
**Raises:** `EncodingError` if data is not valid UTF-8 or contains mojibake

**Usage:**
```python
data = subprocess.check_output(['git', 'log'])
text = EncodingGate.assert_clean_bytes(data, source="git log")
```

---

### Cleanup Methods (for repair)

#### `strip_bom(data)`

Removes Byte Order Mark from bytes.

**Supported BOMs:**
- UTF-8: `EF BB BF`
- UTF-16 LE: `FF FE`
- UTF-16 BE: `FE FF`

**Returns:** `(cleaned_data, bom_type)`
- `cleaned_data`: bytes with BOM removed
- `bom_type`: "UTF-8", "UTF-16-LE", "UTF-16-BE", or `None`

**Usage:**
```python
data = Path("file.txt").read_bytes()
cleaned, bom = EncodingGate.strip_bom(data)
if bom:
    print(f"Removed {bom} BOM")
```

---

#### `strip_control_chars(data)`

Removes null bytes and control characters (except newline/CR).

**Removes:**
- Null bytes (0x00)
- Control chars (0x01-0x1F) except 0x0A (newline) and 0x0D (CR)

**Returns:** `(cleaned_data, removed_count)`

**Usage:**
```python
data = b'Hello\x00World\x01'
cleaned, count = EncodingGate.strip_control_chars(data)
# cleaned = b'HelloWorld', count = 2
```

---

#### `repair_mojibake(text)`

Attempts to invert cp1251-as-utf8 mojibake via round-trip decoding.

**Algorithm:**
1. Locate mojibake runs with regex
2. For each run: `chunk.encode('cp1251').decode('utf-8')`
3. Verify recovery is complete (no U+FFFD, no mojibake signature)

**Returns:** `(result, is_repairable)`
- `result`: repaired text (or original if unrepairable)
- `is_repairable`: `True` if any mojibake was fixed

**Usage:**
```python
corrupted = "РџСЂРѕРµРєС‚"  # mojibake
repaired, fixed = EncodingGate.repair_mojibake(corrupted)
# repaired = "Проект", fixed = True
```

---

#### `clean_file(path, *, repair_mojibake=True, strip_bom=True, strip_control=True)`

Comprehensive file cleanup combining all operations.

**Operations (in order):**
1. Strip BOM (if `strip_bom=True`)
2. Remove control chars (if `strip_control=True`)
3. Decode as UTF-8 (with `errors='replace'` fallback)
4. Repair mojibake (if `repair_mojibake=True`)
5. Write back to disk (only if changes were made)

**Returns:** `(changed, changes)`
- `changed`: `True` if file was modified
- `changes`: List of change descriptions

**Usage:**
```python
from pathlib import Path

path = Path("~/.claude/memory/handoff.md").expanduser()
changed, changes = EncodingGate.clean_file(path)

if changed:
    print(f"Fixed {path.name}:")
    for change in changes:
        print(f"  - {change}")
```

**Example output:**
```
Fixed handoff.md:
  - BOM (UTF-8) removed
  - Control chars removed (3 bytes)
  - Mojibake repaired
```

---

#### `scan_file(path)`

Non-destructive scan for encoding issues.

**Returns:** `Optional[str]`
- `None` if file is clean
- Human-readable issue description if problems found

**Usage:**
```python
issue = EncodingGate.scan_file(Path("handoff.md"))
if issue:
    print(f"Encoding issue: {issue}")
```

Used by `memory_lint.py --validate-encoding`.

---

## Integration Points

### 1. Hot-Memory Write Hooks

**Files:** `auto-remember.py`, `autosave-context.py`, `precompact-flush-l4.py`

```python
from memory_lint_helpers import EncodingGate

# Before writing to handoff.md
text = generate_session_summary()
EncodingGate.assert_clean(text, source="session summary")

with open(handoff_path, 'a', encoding='utf-8') as f:
    f.write(text)
```

---

### 2. Memory Lint Validation

**File:** `memory_lint.py`

```bash
# Scan for encoding issues
python memory_lint.py --validate-encoding

# Repair corrupted files
python memory_lint.py --repair-mojibake --apply
```

---

### 3. Git Activity Detector

**File:** `git-activity-detector.py`

```python
# Validate git log output before writing
git_output = subprocess.check_output(['git', 'log', '--oneline', '-5'])
text = EncodingGate.assert_clean_bytes(git_output, source="git log")
```

---

## Common Patterns

### Pattern 1: Subprocess Output

```python
# ✅ CORRECT - decode with proper codepage
import subprocess
from memory_lint_helpers import EncodingGate

# Windows subprocess (cp1251)
proc = subprocess.run(
    ['git', 'log'],
    capture_output=True,
    encoding='cp1251'  # or 'cp866' for cmd.exe
)
text = proc.stdout

# Validate before writing
EncodingGate.assert_clean(text, source="git log")
```

---

### Pattern 2: File Cleanup

```python
# Clean all memory files
from pathlib import Path
from memory_lint_helpers import EncodingGate

memory_dir = Path.home() / ".claude" / "memory"
for md_file in memory_dir.glob("*.md"):
    changed, changes = EncodingGate.clean_file(md_file)
    if changed:
        print(f"{md_file.name}: {', '.join(changes)}")
```

---

### Pattern 3: Batch Repair

```python
# Repair all corrupted files in a project
import sys
from pathlib import Path
from memory_lint_helpers import EncodingGate

def repair_project(project_path):
    """Repair all markdown files in project."""
    fixed_count = 0
    
    for md_file in Path(project_path).rglob("*.md"):
        changed, changes = EncodingGate.clean_file(md_file)
        if changed:
            print(f"✅ {md_file.relative_to(project_path)}")
            for change in changes:
                print(f"   - {change}")
            fixed_count += 1
    
    print(f"\nFixed {fixed_count} files")

if __name__ == "__main__":
    repair_project(sys.argv[1])
```

---

## Troubleshooting

### Issue: UnicodeEncodeError in Windows console

**Symptom:**
```
UnicodeEncodeError: 'charmap' codec can't encode character '\U0001f4a1' in position 28
```

**Solution:** Add UTF-8 reconfigure at script start:
```python
import sys

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
```

---

### Issue: False positives on legitimate text

**Symptom:** `EncodingGate.assert_clean()` raises on valid Russian text like "СССР" or "РОССИЯ"

**Cause:** Broader mojibake detector uses round-trip test to filter false positives

**Solution:** This is already handled - legitimate uppercase patterns pass the round-trip check

---

### Issue: Mojibake not detected

**Symptom:** Corrupted text passes validation

**Possible causes:**
1. Double-encoded mojibake (mojibake of mojibake)
2. Non-cp1251 encoding (cp866, koi8-r, etc.)
3. Mixed encodings in same file

**Solution:** Manual inspection required - `repair_mojibake()` only handles single-level cp1251 corruption

---

## Testing

### Run EncodingGate tests

```bash
cd claude-4layer-memory
python -m pytest tests/test_encoding_gate_cleanup.py -v
```

**Test coverage:**
- 23 tests covering all methods
- BOM detection (UTF-8, UTF-16 LE/BE)
- Control char removal
- Mojibake repair
- Integration scenarios

---

## Performance

### Benchmarks (on 1MB memory file)

| Operation | Time | Notes |
|-----------|------|-------|
| `strip_bom()` | <1ms | Single prefix check |
| `strip_control_chars()` | ~5ms | Byte-by-byte scan |
| `repair_mojibake()` | ~20ms | Regex + round-trip |
| `clean_file()` (full) | ~30ms | All operations |

**Recommendation:** Use `clean_file()` for batch repair, `assert_clean()` for real-time validation.

---

## Version History

### v1.3.1 (2026-05-07)
- ✅ Added `strip_bom()` method
- ✅ Added `strip_control_chars()` method
- ✅ Added `clean_file()` comprehensive cleanup
- ✅ 23 new tests (100% pass rate)
- ✅ UTF-8 reconfigure in CLI scripts

### v1.3.0 (2026-04-26)
- Initial EncodingGate implementation
- `assert_clean()`, `assert_clean_bytes()`, `repair_mojibake()`, `scan_file()`
- Integration in hot-memory hooks

---

## See Also

- [Memory Lint Documentation](MEMORY_LINT.md)
- [Troubleshooting Guide](TROUBLESHOOTING.md)
- [Code Quality Guide](CODE_QUALITY.md)
