# CLAUDE.md — Digital Portfolio Tracker

Read this file first. Then read the docs in this order:

1. `docs/PRD.md` — what to build (goals, requirements FR-01 to FR-32, data model)
2. `docs/architecture.md` — how the parts fit (adapter, database, API, web app, Radar agent)
3. `docs/radar-agent.md` — the built-in agent "Radar" (checks, routines, rules, moods)
4. `docs/design-system.md` — colours, fonts, components, layout
5. `design/screens/` — the approved screen designs (HTML). Match them.
6. `docs/research-agents.md` — background only (gap review, market agents)

## What this app is

A read-only portfolio tracker for City Holdings. It reads projects every night from
JIRA, OpenProject and Multica, shows them in one place, and has one agent, Radar,
that checks every project and tells people what needs attention.

## Hard rules (never break these)

- **Read-only to the sources.** Never add a write call to JIRA, OpenProject or Multica.
- **No edit controls for project data** anywhere in the UI. Changes happen in the source tool.
- **Radar never sends without approval.** Every digest, email or Teams message is a draft
  until a named person approves it.
- **Rules first, LLM second.** Health and data-quality checks are plain code rules.
  The LLM only writes summaries and answers questions, and always shows its evidence.
- **No secrets in code.** Use environment variables or the secret store.
- **When a source field is unclear, stop and ask.** Do not guess a mapping.

## How to work

- Build in the phases in `docs/PRD.md` → "Build plan". Finish and test each phase before the next.
- Start every phase with a short plan. Keep the plan in `docs/progress.md` and tick items off.
- Use mock connectors with the sample data in `design/sample-data.json` until real API access exists.
- Write tests with each feature (connector tests use recorded API responses).
- UI copy: plain, simple international English. Short sentences, everyday words.

## Stack (decided 19 Oct 2026, see `docs/architecture.md`)

- **MCP-first:** every read and action goes through the City MCP Gateway
  (FastAPI + official Python MCP SDK). Nothing else connects to the database or the trackers.
- Connectors: httpx, GET only, inside the source servers
- Agent: Agno 2.5 as an MCP client
- Database: PostgreSQL (schema `app` for data, `mcp` for registry and audit), SQLAlchemy, Alembic
- Schedules: APScheduler
- Web: SvelteKit + Svelte 5, Tailwind 4 with tokens from `docs/design-system.md`;
  server load functions call MCP
- Auth: City SSO via Microsoft Entra ID (OIDC), user token passed to the gateway
- Run locally with one command: `docker compose up`
- **Agents draft, people approve:** `decide_approval` accepts only a human approver.

## Open questions (ask the user before guessing)

See the end of `docs/PRD.md`. The most important: CTO prototype stack and location,
Multica API access, how "% done" is calculated, and the health (RAG) rule.
