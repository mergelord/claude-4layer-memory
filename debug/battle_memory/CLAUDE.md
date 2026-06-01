# Global Rules — Battle CLAUDE.md (full forensic copy)

See: debug/battle_memory/handoff.md for session history
See: debug/battle_memory/settings.json for hook configuration

This file contains the full CLAUDE.md as extracted from C:\Users\MYRIG\.claude\
on 2026-06-02.

---
KEY SECTIONS SUMMARY FOR FORENSIC ANALYSIS ---

## Anti-Hallucination Rules (ALWAYS active)
- Truth Protocol v1 enforced
- Claims classified as: Verified / Inference / Unknown
- Memory/handoff/decisions do NOT prove external truth
- Current model, effort level, routing config require FRESH verification
- Cannot assert "fixed", "verified", "exactly", "saved $X" without source
- Tool errors must be reported, not papered over

## Model Routing (MANDATORY)
Three-tier routing:
1. DIRECT TOOL CALLS (no subagent): Read, Write, Edit, Grep, Glob, Bash
2. HAIKU SUBAGENT (complex processing): multi-step ops, large data
3. OPUS/SONNET (reasoning): code writing, architecture, debugging

Enforcement protocol:
- Simple I/O → announce NOTHING, just call tool directly
- Haiku subagent → announce BEFORE, use, show savings AFTER
- Opus/Sonnet → current model executes directly

NO EXCEPTIONS clause — violations logged to routing_violations.db

## Hooks (from settings.json)
SessionStart (6 hooks):
  1. routing-protocol-injector.py
  2. inject-verified-facts.py
  3. crash-recovery.py
  4. load-context-on-start.py
  5. memory_lint.py --layer 1 --quick
  6. routing-coordinator.py

PreToolUse (3 hooks):
  1. pre-tool-call-routing-enforcer.py
  2. auto-remember.py
  3. semantic_search.py

Stop (3 hooks):
  1. routing-compliance-reporter.py
  2. session-usage-logger.py
  3. graceful-shutdown-wrapper.py

Model: claude-opus-4-8 (in settings.json)
Effort: high
