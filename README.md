# Portfolio Radar — Digital Portfolio Tracker

Read-only portfolio tracker for City Holdings, with the built-in agent **Radar**.
It reads projects from JIRA, OpenProject and Multica every night. Everything goes
through one **City MCP Gateway**: the nightly sync, the web app, Radar, other
agents and the Notifier. One guard checks every call and one audit log records it.

- Architecture: [`docs/architecture.md`](docs/architecture.md)
- Build plan and progress: [`docs/progress.md`](docs/progress.md)
- Requirements: [`docs/PRD.md`](docs/PRD.md) · Radar: [`docs/radar-agent.md`](docs/radar-agent.md)
- Approved designs: [`design/screens/`](design/screens/)

## What is in the box

| Part | Folder | What it does |
| --- | --- | --- |
| City MCP Gateway | `backend/app/mcp/` | MCP servers `/jira` `/openproject` `/multica` (in) and `/portfolio` `/radar` `/notify` `/admin` `/omni` `/system` (out). Guard: token → caller kind → role → tool on and approved → rate limit → trim fields → remove PII → audit |
| Connectors | `backend/app/connectors/` | Read-only (GET only) client, mock connector on the sample data |
| Nightly sync | `backend/app/adapter/` | Prefix rule, status mapping, stale sources, health rule, snapshots |
| Radar | `backend/app/radar/` | Rule checks, morning message, asks, drafts, chat answers (Agno + LLM, or rules), Notifier |
| Worker | `backend/app/worker.py` | Nightly sync + Radar check, Monday stale check, chat answers, sending approved drafts |
| Web app | `web/` | SvelteKit screens from the designs; an MCP client, nothing else |

## Run it

### With Docker

```bash
docker compose up --build
docker compose exec mcp python -m app.adapter demo     # sample data, history, Radar's first check
```

Open http://localhost:3000 and pick a sample user (dev sign-in). The gateway is on
http://localhost:8000 (`/healthz`, `/readyz`; every MCP endpoint needs a bearer token).

### Without Docker

Needs Python 3.12+, Node 22 and PostgreSQL 16.

```bash
# gateway
cd backend
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
alembic upgrade head
uvicorn app.main:app --port 8000

# sample data (dev only), in another terminal
python -m app.adapter demo

# worker (sync, Radar, Notifier)
python -m app.worker

# web app
cd ../web && npm install && cp .env.example .env && npm run dev   # http://localhost:5173
```

## Tools start off

Every MCP tool starts **off**, and a tool whose description, inputs or access rules
change in code waits for its owner's review (Uber's MCP Gateway pattern). Owners
use the Admin page (MCP tools section) or the command line:

```bash
python -m app.mcp.cli tools                               # every tool and its status
python -m app.mcp.cli on "portfolio.*" --by "Your Name"   # all tools on one server
python -m app.mcp.cli changes                             # changes waiting for review
python -m app.mcp.cli approve 1 --by "Your Name"
python -m app.mcp.cli calls                               # latest audit rows
```

The `demo` command turns everything on for you (dev only).

## Who can do what

| Caller | Examples | Can |
| --- | --- | --- |
| Person, viewer | CTO, Steering Committee, teams | Read the portfolio, talk to Radar, manage Radar's memory |
| Person, approver | PMO | Also answer Radar's questions and approve, edit or reject drafts |
| Person, admin | Portfolio owner (IT) | Also Admin: sources, prefixes, schedule, Radar rules, alerts, tools, audit |
| Agent | Radar chat, CityGPT, other City agents (`/omni`) | Read the portfolio, draft. Never approve or send |
| Service | adapter, radar-job, notifier | Read trackers (adapter), post findings and drafts (radar-job), send approved drafts (notifier) |

Roles come from City SSO groups (`ENTRA_GROUP_ROLES`), or from sample users in dev.

## Settings that need real values

| Setting | Where | For |
| --- | --- | --- |
| `ENTRA_TENANT_ID`, `ENTRA_AUDIENCE`, `ENTRA_GROUP_ROLES` | backend | Gateway checks City SSO tokens |
| `ENTRA_TENANT_ID`, `ENTRA_CLIENT_ID`, `ENTRA_CLIENT_SECRET`, `ENTRA_API_SCOPE` | web | Sign-in with City SSO |
| `SOURCE_MODE=live` + connector settings | backend | Real JIRA / OpenProject / Multica (to build once API access is confirmed) |
| `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL` | backend | Radar's wording and chat (CityGPT, Azure OpenAI, …). Empty = rule-based |
| `TEAMS_WEBHOOK_URL`, `SMTP_*`, `NOTIFY_EMAIL_TO` | backend | Sending approved digests and nudges |
| `DEV_LOGIN=false`, `APP_ENV=prod` | both | Production: no sample users, no dev tokens |

## Tests

```bash
cd backend && . .venv/bin/activate && pytest       # 80 tests; needs a radar_test database
cd web && npm run check && npm run test:e2e        # types; browser tests against a running stack
```

## Rules

Read-only to the sources. No edit controls for project data. Radar never sends
without a person's approval. Rules first, LLM second. No secrets in code.
Details in [`CLAUDE.md`](CLAUDE.md).
