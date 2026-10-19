# Build progress

Plan v1 · 19 Oct 2026 · Architecture: `docs/architecture.md` (MCP-first)

Rule: finish and test each phase before the next. Tick items off as they are done.

## Phase 1 — Foundation and MCP gateway core ✅ (19 Oct 2026, 35 tests pass)

Goal: `docker compose up` starts Postgres and the gateway; the guard works; tests pass.

- [x] Repo layout: `backend/` (FastAPI), `docker-compose.yml` (`db`, `mcp`). `worker` and `web` come with their phases
- [x] Settings from environment variables (`.env.example`, no secrets in code)
- [x] PostgreSQL schemas `app` and `mcp`; Alembic migrations for the PRD data model
- [x] Registry tables: `mcp.server`, `mcp.tool` (owner, version, description, roles, callers, status), `mcp.tool_change`, `mcp.call` (audit)
- [x] Gateway skeleton: FastAPI app, MCP SDK with Streamable HTTP, one endpoint per server, `/healthz`, `/readyz`
- [x] Guard: token check (dev tokens now, Entra ID in Phase 5), caller type (human, agent, service), tool role, tool status (off by default), rate limit
- [x] Field projection (`fields` list) and PII removal (emails, phone numbers)
- [x] Audit row for every call, allowed or blocked
- [x] Tests: blocked when tool is off, wrong role, wrong caller type; projection; PII; audit row written

## Phase 2 — Connectors and source servers ✅ mock (real connectors wait for API access)

- [x] Connector interface and mock connector reading `design/sample-data.json`
- [x] GET-only HTTP client (refuses any other method) with retry and back-off
- [x] `/jira/mcp`, `/openproject/mcp`, `/multica/mcp` on the mock connector
- [ ] Real JIRA and OpenProject connectors once access is confirmed (recorded responses for tests)
- [x] Tests: GET only, retry and back-off, failed source reported clearly (Multica token expired)
- [x] Owner CLI until the Admin page exists: `python -m app.mcp.cli tools | on | off | changes | approve | reject | calls`
- [x] Changed tools move to review and need owner approval (Uber pattern)

## Phase 3 — Adapter, health rule, snapshots ✅ (49 tests pass; health matches all 10 design colours)

- [x] Adapter as MCP client of the source servers (service token)
- [x] Prefix filter (longest match, case-insensitive), non-compliant list, duplicate code flag
- [x] Status mapping from config; sync log; stale handling (FR-08, FR-09)
- [x] Health rule (FR-17) with thresholds as settings; daily snapshots (FR-18); "what changed"
- [x] Scheduler: 02:00 sync
- [x] Tests: prefix rule, health rule, stale source

## Phase 4 — App servers

- [ ] `/portfolio/mcp`: `get_overview`, `list_projects`, `get_project`, `get_history`, `get_sync_status`
- [ ] `/admin/mcp`: sources, prefixes, schedule, `run_sync`, sync log, non-compliant, `set_tool_status`
- [ ] `/omni/mcp`: `discover_server`, `discover_tools`, `get_tool_schema`, `invoke_tool`
- [ ] End-to-end test with a real MCP client

## Phase 5 — Web app and SSO

- [ ] SvelteKit with design tokens, floating menu; server load functions call MCP
- [ ] Overview, Project detail, Admin (match `design/screens/`)
- [ ] City SSO (Entra ID); user token passed to the gateway; Admin and Approver groups
- [ ] Overview under 3 s for 500 projects (cache until next sync)

## Phase 6 — Radar Checker

- [ ] `/radar/mcp`: conversation, findings, `save_findings`
- [ ] Rule checks after sync (02:10); run log
- [ ] Radar screen with findings and questions

## Phase 7 — Radar Reporter

- [ ] `create_draft`, `decide_approval` (human approver only), `/notify/mcp`, Notifier
- [ ] Weekly digest, nudges, alerts; approval log

## Phase 8 — Radar Assistant

- [ ] Agno agent answers questions with evidence, as MCP client
- [ ] Teams channel

## Phase 9–11

- [ ] Roadmap, Risks, strategy tags (`get_roadmap`, `get_dependencies`, `get_risks`)
- [ ] Phone and iPad layouts
- [ ] Full test pass and README

## Decisions made

| Date | Decision |
| --- | --- |
| 19 Oct 2026 | Stack: FastAPI, Agno, PostgreSQL, SvelteKit, Tailwind 4 (matches other City repos) |
| 19 Oct 2026 | MCP-first: every read and action goes through the City MCP Gateway |
| 19 Oct 2026 | Connectors are plain REST (GET only) inside source servers, not third-party MCP servers |
| 19 Oct 2026 | Build our own gateway with ideas from Uber's MCP Gateway; no AutoCrawler for now |
| 19 Oct 2026 | Sample data `red/amber/green/done` maps to Off track / At risk / On track / Done |
| 19 Oct 2026 | Source servers share one tool set (`list_projects`, `get_project`, …) so the adapter treats every source the same |
| 19 Oct 2026 | MCP Python SDK 2.x (`MCPServer`); the guard is SDK middleware that takes over `tools/list` and `tools/call` |
| 19 Oct 2026 | Sample data now has placeholder owners (`<team> lead (sample)`); Agent Ops Console has none, as in the designs |
| 19 Oct 2026 | Unknown tracker status stops that project syncing and is logged (no guessing); mapping in `backend/config/status_map.json` |
| 19 Oct 2026 | `python -m app.adapter demo` loads sample data with 6 weeks of history (dev only) |

## Open questions

- [ ] Gateway only for Portfolio Radar, or shared by all City agents?
- [ ] LLM endpoint for Radar: CityGPT, Azure OpenAI or Claude?
- [ ] JIRA and OpenProject: cloud or self-hosted? Read-only tokens from whom?
- [ ] Multica: is there an API, and who owns access?
- [ ] How is "% done" calculated? Confirm health thresholds.
- [ ] Who is the admin, and who approves Radar's messages?
- [ ] Hosting: Azure or on-premise?
- [ ] Final Radar face (`design/radar-face-options.png`)
- [ ] Missing `support.js` for the screen files in `design/screens/` (needed only to preview them)
