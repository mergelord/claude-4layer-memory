# Claude 4-Layer Memory — Hooks

Hooks extend Claude Code's behavior at specific lifecycle events. This directory contains the built-in hooks that ship with the 4-layer memory system, plus optional hooks for advanced use cases.

## Directory Structure

```
hooks/
├── git-activity-detector.py   # Detects git activity → writes to memory
├── stop_handoff_universal.py  # Stop hook → session summary + rotation
├── builtin/                   # Essential hooks (installed by default)
│   ├── auto-remember.py       # "запомни: X" → writes to HOT memory
│   ├── graceful-shutdown-wrapper.py  # Guarantees Stop hooks execute
│   ├── hook_cache.py          # Caching layer for heavy operations
│   ├── inject-verified-facts.py  # Anti-hallucination (CWD, user, date)
│   ├── load-context-on-start.py  # Loads MEMORY.md/decisions.md at start
│   ├── precompact-flush-l4.py  # Saves memory to vector DB before compact
│   └── session-usage-logger.py  # Logs token usage for cost tracking
└── optional/                  # Optional hooks (install manually)
    └── crash-recovery.py      # Restores context after session crash
```

## What Gets Installed

`install.bat` / `install.sh` automatically copies:
- `git-activity-detector.py` and `stop_handoff_universal.py` (from `hooks/`)
- All `hooks/builtin/*.py` (essential hooks)

> **⚠️ Important:** Copying hooks to `~/.claude/hooks/` does NOT activate them.
> You must register them in `~/.claude/settings.json` under the appropriate
> event (SessionStart, Stop, UserPromptSubmit, PreCompact). See
> [Registering Hooks](#registering-hooks) below.

Optional hooks must be copied manually:
```bash
cp hooks/optional/crash-recovery.py ~/.claude/hooks/
```

## Built-in Hooks (builtin/)

| Hook | Purpose | Critical? |
|------|---------|-----------|
| `precompact-flush-l4.py` | Saves HOT/WARM memory to vector DB before compaction | Yes — data loss without it |
| `session-usage-logger.py` | Logs token usage to SQLite for cost tracking | Yes — ledger won't update |
| `auto-remember.py` | Catches "запомни: X" → writes to HOT memory | Yes — main memory entry point |
| `load-context-on-start.py` | Loads MEMORY.md, decisions.md, handoff.md at session start | Yes — memory layers stay active |
| `inject-verified-facts.py` | Injects CWD, username, date into context | Recommended — anti-hallucination |
| `graceful-shutdown-wrapper.py` | Wraps all stop-*.py hooks in try-except | Recommended — prevents data loss |
| `hook_cache.py` | Caches heavy operations (ChromaDB, sentence-transformers) | Recommended — performance |

## Optional Hooks (optional/)

| Hook | Purpose | When to use |
|------|---------|-------------|
| `crash-recovery.py` | Restores context after session crash | When you have frequent crashes |

## Adding Your Own Hooks

### Stop Hooks
Drop a file named `stop[-_]*.py` in `~/.claude/hooks/`. The `graceful-shutdown-wrapper.py` auto-discovers and executes all stop hooks (both `stop-*.py` and `stop_*.py` patterns).

### Registering Hooks
Copying a hook to `~/.claude/hooks/` is not enough — you must register it in
`~/.claude/settings.json`. Here's a working configuration:

```json
{
  "hooks": {
    "SessionStart": [{
      "matcher": "",
      "hooks": [
        {"type": "command", "command": "\"C:/Program Files/Python313/python.exe\" C:/Users/YOU/.claude/hooks/load-context-on-start.py"},
        {"type": "command", "command": "\"C:/Program Files/Python313/python.exe\" C:/Users/YOU/.claude/hooks/inject-verified-facts.py"}
      ]
    }],
    "PreCompact": [{
      "matcher": "",
      "hooks": [
        {"type": "command", "command": "\"C:/Program Files/Python313/python.exe\" C:/Users/YOU/.claude/hooks/precompact-flush-l4.py"}
      ]
    }],
    "Stop": [{
      "matcher": "",
      "hooks": [
        {"type": "command", "command": "\"C:/Program Files/Python313/python.exe\" C:/Users/YOU/.claude/hooks/graceful-shutdown-wrapper.py"}
      ]
    }]
  }
}
```

Replace `C:/Users/YOU` with your actual home directory path.

### Other Events
Configure hooks in `~/.claude/settings.json` under the `hooks` key:
```json
{
  "hooks": {
    "SessionStart": [{ "matcher": "", "hooks": [{"type": "command", "command": "..."}] }],
    "Stop": [{ "matcher": "", "hooks": [{"type": "command", "command": "..."}] }],
    "UserPromptSubmit": [{ "matcher": "", "hooks": [{"type": "command", "command": "..."}] }],
    "PreCompact": [{ "matcher": "", "hooks": [{"type": "command", "command": "..."}] }]
  }
}
```

## Testing

```bash
# Run hook-specific tests
pytest tests/test_hooks_encoding_gate.py -v

# Smoke test: verify all builtin hooks compile
python -m py_compile hooks/builtin/*.py
```
