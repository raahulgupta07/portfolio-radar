# Portfolio Radar — Digital Portfolio Tracker

Read-only portfolio tracker for City Holdings, with the built-in agent **Radar**.
It reads projects from JIRA, OpenProject and Multica, and everything goes through
one **City MCP Gateway**: the nightly sync, the web app, Radar and other agents.

- Architecture: [`docs/architecture.md`](docs/architecture.md)
- Build plan and progress: [`docs/progress.md`](docs/progress.md)
- Requirements: [`docs/PRD.md`](docs/PRD.md) · Radar: [`docs/radar-agent.md`](docs/radar-agent.md)
- Approved designs: [`design/screens/`](design/screens/)

## Status

| Phase | State |
| --- | --- |
| 1. Foundation and MCP gateway core | ✅ Done |
| 2. Connectors and source servers | ✅ Mock connector. Real JIRA / OpenProject wait for API access |
| 3–11. Adapter, app servers, web app, SSO, Radar, … | Next |

## Run it

### With Docker

```bash
docker compose up --build
```

The gateway listens on http://localhost:8000. `/healthz` and `/readyz` are open;
every MCP endpoint (`/system/mcp`, `/jira/mcp`, `/openproject/mcp`, `/multica/mcp`)
needs a bearer token.

### Without Docker

Needs Python 3.12+ and PostgreSQL 16.

```bash
cd backend
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env            # edit DATABASE_URL if needed
alembic upgrade head
uvicorn app.main:app --port 8000
```

## Turn tools on

Every tool starts **off**. Its owner turns it on (an Admin page comes in Phase 4):

```bash
python -m app.mcp.cli tools                                  # list tools and status
python -m app.mcp.cli on jira.list_projects --by "Your Name"
python -m app.mcp.cli changes                                # tools changed in code, waiting for review
python -m app.mcp.cli approve 1 --by "Your Name"
python -m app.mcp.cli calls                                  # latest audit rows
```

With Docker, prefix these with `docker compose exec mcp`.

## Call the gateway

Dev tokens are in `backend/.env.example` (they only work when `APP_ENV=dev`).

```python
import asyncio, httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

async def main():
    async with httpx2.AsyncClient(headers={"Authorization": "Bearer dev-adapter"}) as hc:
        async with Client(streamable_http_client("http://localhost:8000/jira/mcp", http_client=hc)) as c:
            r = await c.call_tool("list_projects", {"fields": ["count", "projects[].name"]})
            print(r.structured_content)

asyncio.run(main())
```

## Tests

```bash
cd backend && . .venv/bin/activate
createdb radar_test            # once; tests use TEST_DATABASE_URL or radar_test on localhost
pytest
```

## Rules

Read-only to the sources. No edit controls for project data. Radar never sends
without a person's approval. Rules first, LLM second. No secrets in code.
Details in [`CLAUDE.md`](CLAUDE.md).
