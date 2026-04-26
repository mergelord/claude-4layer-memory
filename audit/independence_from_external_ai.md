# Audit #1 — Independence from External AI APIs

**Date:** 2026-04-25
**Scope:** the `mergelord/claude-4layer-memory` repository as of `main` after PR #10 (`ce8bfac`).
**Question:** does the core memory system call out to any external AI/LLM API (Anthropic, OpenAI, Cohere, Google AI, Mistral, ChromaDB Cloud, Pinecone, ...) directly from its own code paths?

**Short answer:** No. The repo is fully self-contained at the API-dependency level. The only "AI" code path runs locally via `sentence-transformers` (an open-source embedding model loaded from a local Hugging Face cache) and a local ChromaDB persistent client. The agent that sits *above* this system — Claude Code, Devin, Cursor, etc. — is the LLM, but the system itself never initiates an LLM call.

This is the property the system is designed for: anything an LLM does on top of this memory is *opt-in by the user's agent*, not embedded in the system's own code paths.

---

## 1. Method

We checked four classes of dependency in turn:

1. **Direct provider SDKs** — `anthropic`, `openai`, `cohere`, `google-generativeai`, `mistralai`, `replicate`, etc.
2. **Generic HTTP clients** — `requests`, `urllib`, `httpx`, `aiohttp`, `http.client`, JS `fetch`.
3. **Cloud-hosted vector / search backends** — ChromaDB Cloud, Pinecone, Weaviate Cloud, Qdrant Cloud, Postgres-pgvector with managed endpoints.
4. **Subprocess shell-outs that could call out** — `subprocess.run`, `os.system`.

For each, we report what we found and whether it implies a network call to an external AI provider.

## 2. Findings

### 2.1 Direct provider SDK imports — none

```
$ rg "^(import|from)\s+(anthropic|openai|cohere|google\.genai|mistralai|replicate)" --glob '*.py' --glob '*.js'
(no matches)
```

Every reference to the strings `anthropic` or `openai` in the repository is either:

- inside `config/api_keys.example.json` — a placeholder file demonstrating which keys the *user's wider environment* might keep around, not consumed by any code in the repo;
- inside `test_privacy_controls.py` — a test that asserts these filenames are listed in `.gitignore` so the user does not leak keys, again without consuming them.

There is no `from anthropic import ...`, no `openai.ChatCompletion.create(...)`, no `Anthropic(api_key=...)` anywhere in production code paths.

### 2.2 Generic HTTP clients — none

```
$ rg "requests\.|urllib|httpx|aiohttp|http\.client|fetch\(" --glob '*.py' --glob '*.js'
(no matches in scripts/, mcp_server.py, audit.py, cli/, utils/)
```

Nothing in the system opens an outbound socket to an HTTP endpoint. The CLI (`cli/index.js`) uses `commander` and `chalk` only; `mcp_server.py` uses `mcp.server.fastmcp.FastMCP`, which speaks the Model Context Protocol over stdio with the local Claude Code process — not over any network.

### 2.3 Cloud vector / search backends — none

`scripts/l4_semantic_global.py` builds Chroma exclusively as a local persistent client:

```
self.client = chromadb.PersistentClient(
    path=str(db_path),
    settings=Settings(...)
)
```

There is no use of `chromadb.HttpClient`, `chromadb.CloudClient`, or any URL-based constructor. The on-disk database lives next to the user's memory under `~/.claude/semantic_db_global/`. `requirements.txt` pins `chromadb>=0.4.0` and `sentence-transformers>=2.2.0`; both are local.

### 2.4 Subprocess shell-outs — local only

Subprocess usage is restricted to:

- `scripts/l4_fts5_search.py:418` — invokes `git` (local repo).
- `scripts/semantic_search.py:173` — invokes `sys.executable` to run `l4_semantic_global.py` as a child process for the auto-search hook (still local).
- `test_privacy_controls.py` — invokes `git` to verify ignored files.

None of these spawn a network client.

### 2.5 The semantic / embedding path

The single "ML" path in the system is:

1. `SentenceTransformer(model_name)` loads a model (default `all-MiniLM-L6-v2`) from the local Hugging Face cache (`~/.cache/huggingface/`).
2. `chromadb.PersistentClient` stores embeddings in `~/.claude/semantic_db_global/`.

`sentence-transformers` *will* fetch the model weights from HuggingFace Hub on first use if they aren't cached. This is the only remote download in the system, it is one-shot, it is not an inference call, and the model itself runs entirely locally afterwards. We surface this in §4 below.

### 2.6 The "Layer 2" semantic checks in `memory_lint.py`

`scripts/memory_lint.py` has methods named `check_contradictions`, `check_outdated_claims`, etc. that *build prompts* but do not *send* them. The system formats statements and constructs a prompt string; whether that prompt is shown to an LLM is up to the agent that loads the system (Claude Code, Devin, Cursor). The system itself never makes the call.

This matters: it is the architectural choice that makes the repo independent. The deterministic layer prepares evidence; the LLM layer (sitting one step up the stack) optionally consumes it.

## 3. Verdict

| Class of dependency | Found in code? | Verdict |
| --- | --- | --- |
| Anthropic / OpenAI / other LLM SDKs | No | ✅ Independent |
| Generic outbound HTTP from Python code | No | ✅ Independent |
| Generic outbound HTTP from JS code | No | ✅ Independent |
| Cloud vector / search backend | No (local Chroma only) | ✅ Independent |
| Subprocess to a network tool | No (only `git`, `python`) | ✅ Independent |
| Local ML model | Yes (`sentence-transformers`, local) | ✅ Local-only inference |
| Initial model download from HuggingFace Hub | Yes, one-shot per model | ⚠️ See §4 |

## 4. Caveats and follow-ups

### 4.1 First-run model download

`sentence-transformers` will attempt to fetch model weights from the HuggingFace Hub on first use. After that, the cache lives in `~/.cache/huggingface/` and no further network traffic is required.

**Recommendation:** ship a small "cold-start" subcommand (e.g. `claude-memory-cli prefetch`) that downloads the configured model up front and writes a marker file. Then offline-only environments can run the prefetch once on a connected box, copy the cache, and operate fully offline.

### 4.2 Optional cloud Chroma / cloud HuggingFace are *possible*

The system currently never instantiates them, but a contributor could add `chromadb.HttpClient(...)` or `huggingface_hub.InferenceClient(...)` and break this property silently. There is no automated check that fails CI on such an addition.

**Recommendation:** add a lint rule (or a simple `pytest` test) that scans the source tree for the substrings `HttpClient`, `CloudClient`, `InferenceClient`, `requests.`, `httpx.`, `aiohttp.`, etc. and fails if they appear in production code paths. This makes the independence property a tested invariant rather than a manual claim.

### 4.3 The `mcp[cli]` package

`mcp_server.py` imports `mcp.server.fastmcp.FastMCP`. The `mcp` package itself is by Anthropic, but the protocol it implements (Model Context Protocol) is local-stdio between two processes on the same machine. There is no outbound network call inside `FastMCP.run()`.

**Recommendation:** none. Document in the README that MCP is a transport protocol, not an API; this confuses readers who assume "it's by Anthropic so it must talk to Anthropic".

### 4.4 The user's own setup (`~/.claude/settings.json`) can break this

A user is free to add hooks that *do* call OpenAI/Anthropic. The system can't prevent that; it only guarantees its own code doesn't do it.

**Recommendation:** the deploy-script we ship for syncing `~/.claude/` should include an optional final check: parse `settings.json`, list every `hooks/*` referenced, and grep each referenced script for outbound HTTP. Surface a warning if any user hook performs network calls. This is informational, not blocking.

## 5. Test invariant (suggested)

Add `tests/test_independence_invariant.py`:

```python
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CODE_DIRS = ["scripts", "cli", "utils", "."]
CODE_GLOBS = ["*.py", "*.js"]
EXCLUDE_FILES = {"test_privacy_controls.py", "audit.py"}  # documented exceptions

FORBIDDEN = re.compile(
    r"\b(requests|httpx|aiohttp|http\.client|urllib\.request)\.|"
    r"chromadb\.HttpClient|chromadb\.CloudClient|"
    r"huggingface_hub\.InferenceClient|"
    r"^\s*(import|from)\s+(anthropic|openai|cohere|mistralai|replicate)\b",
    re.MULTILINE,
)


def test_no_external_ai_api_calls():
    offenders = []
    for d in CODE_DIRS:
        base = ROOT / d
        if not base.exists():
            continue
        for g in CODE_GLOBS:
            for path in base.rglob(g):
                if path.name in EXCLUDE_FILES:
                    continue
                if "/.venv/" in str(path) or "/node_modules/" in str(path):
                    continue
                if "/__pycache__/" in str(path):
                    continue
                text = path.read_text(encoding="utf-8", errors="ignore")
                if FORBIDDEN.search(text):
                    offenders.append(str(path.relative_to(ROOT)))
    assert not offenders, (
        "Files introduce external AI/HTTP dependencies, breaking the "
        "independence-from-external-AI property:\n"
        + "\n".join(f"  - {p}" for p in offenders)
    )
```

This codifies the audit so any future PR that introduces a real external dependency has to delete or modify the test, making the change visible.

---

## Appendix A — files inspected

- `mcp_server.py`, `audit.py`, `analyze_project.py`, `test_privacy_controls.py`
- `scripts/`: `l4_semantic_global.py`, `l4_fts5_search.py`, `memory_lint.py`,
  `memory_lint_helpers.py`, `semantic_search.py`, `cost_tracker.py`,
  `cleanup_system_artifacts.py`, `skill_creator.py`,
  `antipattern_checkers.py`, `consistency_checkers.py`
- `cli/`: `index.js`, `commands/init.js`, `commands/search.js`, `commands/lint.js`,
  `commands/build.js`
- `utils/`: `colors.py`, `base_reporter.py`
- `requirements.txt`, `package.json`, `config/api_keys.example.json`,
  `config/semantic_config.json`, `config/memory_lint_config.yml`

## Appendix B — related decisions

- PR #10 added `_normalize_id_part` (uses `hashlib.md5(usedforsecurity=False)` for non-cryptographic chunk-ID derivation, no network).
- PR #9 fixed `mcp_server.reindex_memory` (renamed to `reindex_all`, no network).
- PR #7/#8 extracted `consistency_checkers.py` and `antipattern_checkers.py`; both
  are pure regex/string checks, no network.
