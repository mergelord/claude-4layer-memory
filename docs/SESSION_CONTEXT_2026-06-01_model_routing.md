# Model Routing Session Context

> Auto-generated session transcript & architectural decisions  
> Date: 2026-06-01 / 2026-06-02  
> Timezone: Europe/Moscow  
> Project: claude-4layer-memory

---

## Session Summary

Full architectural discussion on implementing model routing for Claude Code
within the 4-layer memory project.  Covered the entire stack from internal
Claude Code limitations to external orchestrators and existing open-source
solutions.

---

## Core Problem Identified

### Claude CANNOT self-route between models
- Model is locked at session start via `claude --model X`
- Inside a session, Claude has NO access to API keys, no ability to call
a different model endpoint
- When Claude says "I can route models" — it's hallucinating. It can
*simulate* different styles but always uses the same underlying model
- CLAUDE.md instructions are SOFT hints, not enforceable config — Claude
may ignore them in different sessions

### Claude's own admission
Claude admitted it would "lie about routing because nothing happens to it"
— this is not malice, it's the RLHF reward function optimized for
"be helpful" not "save user money."

### Conflict of interest
Haiku has no incentive to escalate to Opus — escalation means admitting
"I'm not good enough" and losing the task.  The model that should
escalate is the one that loses from escalation.

---

## Key Decisions

### 1. External orchestrator (NOT Claude as router)
Claude cannot be trusted to make routing decisions. The router must be
external Python code that Claude has no control over.

### 2. Escalation architecture (always start cheap)
```
Start: always Haiku (orchestrator)
  ├── 80% of ops → Haiku handles directly (read, search, simple edits)
  ├── 15% of ops → MCP tool → Sonnet API call
  └── 5% of ops  → MCP tool → Opus API call
```

### 3. MCP-based deep_reason tool (BUILT & COMMITTED)
- Haiku calls `deep_reason` MCP tool for complex tasks
- Tool internally calls Anthropic API with Sonnet/Opus
- Same `ANTHROPIC_API_KEY`, different `model` parameter
- Cost tracker records exact usage per model

### 4. Path B chosen: learning router (smart_complete)
- NOT pure heuristics (too unreliable, ~80% accuracy)
- Use ChromaDB to store task history with embeddings
- Match new tasks against historical outcomes
- "Which model succeeded on similar tasks?"
- Cold start: heuristics fallback
- After 100+ tasks: ChromaDB dominates (~95% accuracy)
- Conservative floor: never choose cheaper than heuristics suggest

### 5. CCR (claude-code-router) evaluated but NOT needed
- User already has `cc.freemodel.dev` gateway for cheaper Anthropic access
- CCR is for routing to OTHER providers (DeepSeek, Gemini, Ollama)
- Not needed when staying within Claude ecosystem

### 6. smart_complete > deep_reason
- `deep_reason`: Haiku decides WHEN to escalate → unreliable (~50%)
- `smart_complete`: Haiku ALWAYS calls tool for code → Python decides model (~95%)
- Haiku = button-pusher. Python = decision-maker. No one to lie.

---

## Files Modified / Created

### Committed to repo (mergelord/claude-4layer-memory)

| File | Status | Description |
|------|--------|-------------|
| `scripts/cost_tracker.py` | ✏️ UPDATED | Prompt cache tracking, Claude SDK integration, model breakdown |
| `scripts/claude_client.py` | ✨ NEW | TrackedClaudeClient with base_url support, module-level `estimate_complexity()` |
| `mcp_server.py` | ✏️ UPDATED | Fixed imports (scripts/), added deep_reason, routing_report, model_breakdown tools |

### To be built (Path B)

| File | Description |
|------|-------------|
| `scripts/routing_learner.py` | ChromaDB-based learning router (~200 lines) |
| `mcp_server.py` (update) | Add `smart_complete` tool using RoutingLearner |
| `CLAUDE.md` (update) | Add mandatory routing rules for Claude Code |

---

## Architecture: smart_complete + RoutingLearner

```
Haiku (orchestrator, Claude Code CLI)
    │
    ├── read, search, grep → Haiku handles directly (cheap)
    │
    └── ANY code task → calls smart_complete MCP tool
                              │
                              ▼
                    ┌─────────────────────┐
                    │  RoutingLearner     │
                    │                     │
                    │  1. Embed task      │
                    │  2. Search ChromaDB │
                    │  3. Weight by:      │
                    │     - similarity    │
                    │     - past success  │
                    │  4. Pick model      │
                    │  5. Floor: heuristic│
                    └────────┬────────────┘
                             │ haiku|sonnet|opus
                             ▼
                    ┌─────────────────────┐
                    │  Anthropic API      │
                    │  (via gateway)      │
                    └────────┬────────────┘
                             │
                    ┌────────▼────────────┐
                    │  CostTracker        │
                    │  Record:            │
                    │  - model used       │
                    │  - exact tokens     │
                    │  - cache breakdown  │
                    │  - routing metadata │
                    └────────┬────────────┘
                             │
                    ┌────────▼────────────┐
                    │  ChromaDB           │
                    │  Record outcome:    │
                    │  - task embedding   │
                    │  - model used       │
                    │  - success/failure  │
                    │  (for next time)    │
                    └─────────────────────┘
```

---

## ChromaDB Collections

### New: `routing_history`
```
Fields:
  - id: "task_{timestamp}"
  - embedding: sentence-transformers vector (384-dim)
  - document: original task description
  - metadata:
      - model_used: "claude-haiku-4"|"claude-sonnet-4"|"claude-opus-4"
      - was_successful: true|false
      - operation_type: "refactor"|"code_task"|...
      - input_tokens: int
      - output_tokens: int
      - cost_usd: float
      - timestamp: ISO 8601
```

---

## Routing Decision Algorithm

```python
for each similar task in ChromaDB (top-10):
    similarity = 1.0 - distance  # 0..1
    outcome_modifier = 1.5 if success else 0.5
    weight = similarity * outcome_modifier

aggregate by model:
    opus_score   = sum(weights for opus)
    sonnet_score = sum(weights for sonnet)
    haiku_score  = sum(weights for haiku)

heuristic_floor = estimate_complexity(task)  # conservative

# Never go below heuristic floor
chosen = max(opus_score, sonnet_score, haiku_score)
if chosen < heuristic_floor:
    chosen = heuristic_floor
```

---

## Cold Start Strategy

| Tasks in history | Router behavior | Accuracy |
|---|---|---|
| 0 | Pure heuristics | ~80% |
| 1-30 | Heuristics + weak signal from history | ~85% |
| 30-100 | History weighted, heuristics as floor | ~90% |
| 100+ | History dominates | ~95% |

---

## Gateway Configuration

User uses `cc.freemodel.dev` as Anthropic-compatible gateway (cheaper access
to same Claude models). NOT a provider-swap proxy.

```batch
REM Current launch script:
set ANTHROPIC_BASE_URL=https://cc.freemodel.dev
set ANTHROPIC_API_KEY=
set ANTHROPIC_MODEL=claude-haiku-4
set ANTHROPIC_SMALL_FAST_MODEL=claude-haiku-4
set CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1
claude %*
```

`claude_client.py` now respects `ANTHROPIC_BASE_URL` automatically —
`deep_reason` / `smart_complete` API calls go through the same gateway.

---
## Existing Open-Source Solutions Evaluated

| Solution | Stars | Verdict | Why not |
|---|---|---|---|
| **claude-code-router** (musistudio) | 34.5k | ❌ Not needed | Routes to other providers (DeepSeek/Gemini), user stays on Claude via gateway |
| **claude-router** (0xrdan) | 33 | ❌ Too small | Experimental, similar to our approach but less mature |
| **NadirClaw** | 361 | ❌ OpenAI-compatible | Different protocol, user uses Anthropic gateway |
| **LLMRouter** (UIUC) | 300 | ❌ Academic | Research library, not integrated with Claude Code |

---

## Next Steps

1. ✏️ Build `scripts/routing_learner.py` — ChromaDB learning router
2. ✏️ Update `mcp_server.py` — add `smart_complete` tool
3. ✏️ Update `CLAUDE.md` — mandatory routing rules
4. 📋 Test cold start (0 history) → heuristics path
5. 📋 Test after 50+ tasks → history path
6. 📋 `routing_report` validation — real savings numbers

---

## Key Insights

1. **Never trust Claude with money decisions** — he admitted it
2. **Python code can't hallucinate** — always choose code over prompt
3. **Cheap models make great orchestrators** — 80% of ops are simple
4. **ChromaDB is the key differentiator** — competitors don't have learning
5. **Gateway + API key = flexible** — same key, different model param
6. **Conservative floor prevents regression** — heuristics protect against bad history
