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
| 19 Oct 2026 | Tracker field mapping is an admin choice confirmed by a person; live sync refuses until then |
| 19 Oct 2026 | Services get their own rate limit (6,000/min): the sync makes about 4 calls per project |
| 19 Oct 2026 | Worker jobs use one Azure managed identity each to sign in to the gateway |
| 20 Oct 2026 | LDAP through Keycloak, not directly: the app never handles passwords |
| 19 Oct 2026 | Teams chat answers go only to the person who asked, in a 1:1 chat, like the in-app chat; no approval needed for that. Digests still need approval |

## Phase 13: live connectors ✅

- [x] JIRA Cloud (REST v3, `search/jql`) and Data Center (REST v2), GET only, paging, retries
- [x] OpenProject (API v3): projects, statuses, milestones, versions as sprints, work package counts, relations, risks
- [x] Field mapping per tracker in Admin; a live sync reads project fields only after a person confirms it (nothing guessed)
- [x] Live connectors rebuilt from Admin settings without a restart; token from the secret store
- [x] Tests replay recorded responses (`backend/tests/recorded/`); `python -m app.connectors.record` records real ones
- [ ] Multica: needs its API

## Phase 14: load test ✅ (`docs/load-test.md`)

- [x] 500 projects, a year of daily snapshots; overview page 1.2 s (target 3 s)
- [x] Fixed: services hit the people rate limit during the sync; overview and project queries; dependency lookups; tile notes; gzip

## Phase 15: PDF one-pagers ✅

- [x] Project one-pager (A4) and portfolio one-pager for the Steering Committee (A4 landscape), drawn by the gateway

## Phase 16: Azure ✅ (`docs/deploy-azure.md`)

- [x] Bicep: Container Apps, private PostgreSQL, Key Vault, registry, one managed identity per part and per worker job
- [x] Worker jobs sign in to the gateway with managed identities (no stored service tokens)
- [x] GitHub Actions: CI (tests, type check, build, Bicep lint) and deploy (OIDC, `az acr build`, health check)
- [ ] First deployment in City's subscription

## Phase 17: security review ✅ (`docs/security-review.md`)

## Phase 18: Teams chat ✅ (`docs/teams-bot.md`)

- [x] 1:1 chat with Radar in Teams through the gateway; Microsoft's token checked; City tenant only
- [x] Answers go back to the same chat only; digests still need approval
- [ ] First real test with City's bot registration

## Phase 19: sign-in options and People ✅ (`docs/sso.md`)

- [x] City SSO through Keycloak as well as Entra ID (web sign-in and gateway token checks)
- [x] LDAP / Active Directory through Keycloak User Federation; LDAP groups become roles
- [x] Admin → People: who signed in, extra roles for one person, block a person
- [x] Local demo: `docker-compose.sso.yml` with Keycloak and a sample LDAP directory; browser tests against it

## Phase 20: install guide, superadmin, OpenRouter ✅

- [x] README rewritten as an install guide with diagrams, configuration reference and troubleshooting
- [x] Superadmin: local name and password (scrypt hash), viewer + admin, lock-out, audited; optional in Azure
- [x] OpenRouter as an LLM provider, in env or Admin
- [x] Docker Compose reads optional `backend/.env` and `web/.env` for your own values

## Phase 21: Programs (program office view) ✅

- [x] New read-only **Programs** screen: program switcher, KPI tiles that filter, Charter / Projects / RACI tabs
- [x] Charter: manager, sponsor, dates, completeness checklist, status summary, scope, benefits, risks, budget, milestones, measurables, team, steering committee
- [x] Projects table with owner, workstream, next step, decision needed; filters, sort, search (also owners and RACI names)
- [x] Download for Excel (CSV with byte-order mark) of the filtered projects
- [x] Data comes from the program office file: `python -m app.adapter po-import <file>` (tables `app.po_program`, `app.po_project`, migration 0007); tool `portfolio.get_programs`, off until an admin turns it on
- [x] Programs screen rebuilt to the approved mockup: Charter, Projects, Timeline, RACI (by project and by person), Activity (migration 0008, change history imported with the file)
- [ ] Program switcher on Overview, Roadmap and Risks (tracker projects carry no program yet)

## Still open (needs input or access)

- [ ] JIRA and OpenProject read-only tokens, then confirm the field mapping in Admin
- [ ] Multica connector — need to know its API
- [ ] City SSO switched on — need the Entra ID app registrations, group IDs for admin and approver
- [ ] LLM endpoint for Radar's wording and chat (CityGPT, Azure OpenAI or Claude)
- [ ] Teams webhook, Teams bot registration and SMTP
- [ ] Azure subscription and resource group for the first deployment

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
