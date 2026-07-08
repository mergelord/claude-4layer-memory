# Session context (living)

This is a short, living context snapshot for recent sessions / operational decisions.

## 2026-07-09 — Custom Notion agent setup (claude-4layer-memory Dev)

### What was created
- A custom Notion agent **"claude-4layer-memory Dev"** for working on `mergelord/claude-4layer-memory`.

### Integrations
- **GitHub via MCP**: agent can read/write the repository through the configured GitHub MCP server integration.
- **Sentry via MCP**: agent can query monitoring data through the configured Sentry MCP server integration.
- **Notion**: agent can read the workspace and has edit access to selected working pages + the session journal database.

### Triggers
- **@mention trigger**: agent responds when mentioned.
- **New entry trigger**: agent runs automatically when a new page is created in the Notion database **"Журнал сессий — claude-4layer-memory"**.

### Backup protocol
- Session outcomes are recorded in the Notion database **"Журнал сессий — claude-4layer-memory"**.
- This `docs/SESSION_CONTEXT.md` file is used as a lightweight repo-side mirror of important operational context and decisions.

### Notes / constraints
- Notion's native GitHub connector may be unavailable for personal GitHub accounts; the MCP integration is the workaround.
- Notion event triggers operate on databases, so a dedicated session journal database is used.
