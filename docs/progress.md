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

## Phase 4 — App servers ✅

- [x] `/portfolio/mcp`: `get_overview`, `list_projects`, `get_project`, `get_history`, `get_roadmap`, `get_dependencies`, `get_risks`, `get_sync_status`
- [x] `/admin/mcp`: sources, `test_source`, prefixes, settings (schedule, Radar rules, alerts), `run_sync`, sync log, non-compliant, tools, tool changes, audit
- [x] `/omni/mcp`: `discover_server`, `discover_tools`, `get_tool_schema`, `invoke_tool` (only what the caller may use; same guard)
- [x] Tests through the guard for every server (61 tests); HTTP end-to-end test from Phase 1

## Phase 5 — Web app and SSO ✅

- [x] SvelteKit with design tokens, floating menu (desktop, iPad) and phone tab bar; server load functions call MCP
- [x] Overview, Projects, Project detail, Admin (match `design/screens/`); CSV export; print to PDF
- [x] City SSO (Entra ID, code flow with PKCE) in the web app; gateway checks Entra tokens (signature, issuer, audience, expiry) and maps groups to roles; dev sign-in only when DEV_LOGIN=true
- [x] Read results cached per user (60 s); one `get_overview` call per page. Load test with 500 projects still to do

## Phase 6 — Radar Checker ✅

- [x] `/radar/mcp`: conversation (per person, everyone, approvers), findings with first-seen, asks, memory, status and mood
- [x] Rule checks right after the nightly sync: off track, slipping, sync, stale work, no owner, no milestone dates, no sprint goal, got worse this week; run log
- [x] Radar screen as designed: waiting bar, cards (health, findings, dependency, Radar asks, approval), composer, side panel

## Phase 7 — Radar Reporter ✅

- [x] `create_draft` (agents and the Radar job), `decide_approval` (human approvers only, with edit), `/notify/mcp`, Notifier (Teams webhook, SMTP; dev outbox)
- [x] Weekly digest (decisions first, sent at the digest time after approval), nudges after an approver says yes; approval log. External alerts follow the same draft-and-approve path

## Phase 8 — Radar Assistant ✅ (Teams chat open)

- [x] Agno agent with a fixed tool list (each tool wraps one gateway tool) when an LLM is set up; rule-based answers with evidence when not
- [ ] Teams channel (two-way chat in Teams) — not started; Teams is used for sending approved drafts

## Phase 9–11 ✅

- [x] Roadmap (timeline, milestones, today line, dependencies with buffer), Risks (matrix, register incl. sync log and Radar findings, 2030 aspirations with gaps)
- [x] Phone (tab bar, 2×2 tiles, scrolling chips) and iPad (floating menu, narrower panel) layouts
- [x] 80 backend tests, 6 browser tests (also against the full Docker stack), README

## Phase 12 — Connections set up in the app ✅ (91 backend tests, 8 browser tests)

- [x] Secret store: Azure Key Vault (production) or a local file (dev); app keeps only `kv://` names; `set_secret` is write-only and masked in the audit log
- [x] Admin tabs: Settings, Connections, MCP tools, Agents, Activity
- [x] Source set-up: address, Cloud/Data Center, sign-in, service account, token, full check, status mapping (saved in the app), tools
- [x] Sign-in, LLM and sending: City SSO (applies at once), LLM, Teams, SMTP, each with a test; worker reads them through MCP
- [x] Agents: Entra app ID, allowed servers, rate limit, on/off, "test as this agent", address snippet; enforced by the guard
- [ ] "Add a source" for a new tracker type: needs a connector in code first

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
| 19 Oct 2026 | Agno's own MCP connector needs MCP SDK 1.x; Radar uses plain Agno tools that each call one gateway tool instead |
| 19 Oct 2026 | Chat is MCP-only: the web app posts the question, the worker answers through MCP, the page picks it up |
| 19 Oct 2026 | Connections are set up in Admin; secrets go to Key Vault by name only; Admin values win over environment variables |
| 19 Oct 2026 | Web sign-in (client ID and secret) stays a web-container setting; the gateway side of SSO is set in Admin |

## Still open (needs input or access)

- [ ] Real JIRA and OpenProject connectors (`SOURCE_MODE=live`) — need hosting details and read-only tokens
- [ ] Multica connector — need to know its API
- [ ] City SSO switched on — need the Entra ID app registrations, group IDs for admin and approver
- [ ] LLM endpoint for Radar's wording and chat (CityGPT, Azure OpenAI or Claude)
- [ ] Teams webhook and SMTP for sending approved drafts
- [ ] Two-way Teams chat with Radar
- [ ] Load test: overview under 3 s with 500 projects
- [ ] PDF one-pager: today the browser's print to PDF is used

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
