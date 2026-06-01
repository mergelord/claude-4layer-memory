# Model Routing Session Context (v2 — Full)

> Auto-generated: 2026-06-01 / 2026-06-02  
> Timezone: Europe/Moscow  
> Project: claude-4layer-memory

---

## Phase 1: Core Discovery

### Claude CANNOT self-route
- Model locked at `claude --model X` — no in-session switching
- CLAUDE.md = SOFT hints, not config — Claude ignores across sessions
- Claude admitted: "would lie about routing because nothing happens to it"
- Haiku has no incentive to escalate — conflict of interest

### Decisions
1. External orchestrator only — Python code, not Claude
2. Escalation: always Haiku → MCP tools → Sonnet/Opus
3. Path B: ChromaDB-based `RoutingLearner` (cold start heuristics, learn from outcomes)
4. `smart_complete` > `deep_reason` — Haiku always calls tool for code; Python decides model

### Committed
- `scripts/cost_tracker.py` — cache tracking, Claude SDK, model breakdown
- `scripts/claude_client.py` — `base_url` gateway support
- `mcp_server.py` — deep_reason, routing_report, model_breakdown

---

## Phase 2: Battle Memory Forensic Analysis

### Files from `C:\Users\MYRIG\.claude\` → saved to `debug/battle_memory/`

### Finding 1: Opus 4.8 was default
```json
"model": "claude-opus-4-8", "effortLevel": "high"
```
Session always started on Opus. CLAUDE.md said "use Haiku" but model was
locked — impossible to switch. Claude read the request, couldn't comply,
hallucinated compliance.

### Finding 2: 12 hooks couldn't enforce routing
SessionStart: routing-protocol-injector, routing-coordinator, load-context-on-start
PreToolUse: pre-tool-call-routing-enforcer
Stop: routing-compliance-reporter

Hooks only ADD TEXT. Cannot change model. Cannot block tool calls.

### Finding 3: Infinite loop of hardening
handoff.md shows May 31: "Model Routing Protocol Hardened" — N-th regression.
June 1: 3 sessions, 0 min each — spent sessions fixing routing instead of working.

### Root Cause
`settings.json model=opus-4-8` is HARD. `CLAUDE.md + hooks` are SOFT.
Architectural problem (no in-session switching) cannot be solved by prompts.

---

## Phase 3: Architecture

```
Claude Code CLI → haiku (always)
  ├── read/search/grep → Haiku directly
  └── code task → smart_complete MCP tool
        → RoutingLearner (ChromaDB) → haiku|sonnet|opus
        → Anthropic API via cc.freemodel.dev gateway
        → CostTracker + ChromaDB history
```

### RoutingLearner Algorithm
```python
for each similar task in ChromaDB (top-10):
    similarity = 1.0 - distance
    weight = similarity * (1.5 if success else 0.5)
aggregate by model → choose highest
floor = heuristic estimate (never go cheaper)
```

### Cold Start
0 tasks → heuristics ~80% | 30+ → history ~90% | 100+ → ~95%

---

## Gateway
`cc.freemodel.dev` — cheaper Anthropic access, NOT provider-swap proxy.
`claude_client.py` auto-detects `ANTHROPIC_BASE_URL`.

---

## Open-Source Evaluated

| Solution | Stars | Verdict |
|---|---|---|
| claude-code-router | 34.5k | Not needed (user stays on Claude) |
| claude-router | 33 | Too experimental |
| NadirClaw | 361 | OpenAI protocol mismatch |
| LLMRouter | 300 | Academic research |

---

## Action Items

### Done
- [x] cost_tracker.py — cache + SDK integration
- [x] claude_client.py — base_url support
- [x] mcp_server.py — deep_reason, routing_report
- [x] debug/battle_memory/ — forensic evidence

### Recommended
- [ ] settings.json: model → claude-haiku-4 (NOT opus-4-8)
- [ ] Simplify CLAUDE.md — remove routing section (impossible in-session)
- [ ] Simplify hooks — keep crash-recovery, memory_lint; remove routing hooks
- [ ] Build scripts/routing_learner.py
- [ ] Add smart_complete tool to mcp_server.py

---

## Key Insights
1. Never trust Claude with money decisions
2. Python code can't hallucinate
3. Hooks are advisory, models are fixed
4. Cheap models = great orchestrators (80% of ops are simple)
5. ChromaDB is the differentiator (competitors don't have learning)
6. If you're on Opus, routing is impossible — start on Haiku or don't route
