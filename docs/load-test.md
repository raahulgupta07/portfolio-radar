# Load test: 500 projects

PRD requirement: *the overview loads in under 3 seconds for 500 projects.*
Result: **met.** The overview page loads in about 1.2 s and its data in about 0.2 s.

## How to run it

```bash
createdb -O radar radar_load
cd backend
export DATABASE_URL=postgresql+psycopg://radar:radar@localhost:5432/radar_load
alembic upgrade head && python -m app.adapter seed
python -m loadtest.run --projects 500 --days 365      # writes loadtest/results.json

# Pages in a real browser: run a gateway on this database (port 8001) and the built web app against it
uvicorn app.main:app --port 8001 &
cd ../web && npm run build
GATEWAY_URL=http://127.0.0.1:8001 MCP_CACHE_SECONDS=0 DEV_LOGIN=true PORT=5174 node build &
node scripts/loadtest-pages.mjs http://127.0.0.1:5174
```

The script refuses to run unless `DATABASE_URL` names `radar_load`, because the demo loader empties
the portfolio tables.

## What it loads

- 500 generated projects across JIRA, OpenProject and Multica, with real prefixes, milestones,
  sprints, 125 "blocks" links, 100 risks and 20 badly named projects
- 165,000 daily snapshots (a year of nightly syncs for every project)

## Results (19 Oct 2026, dev container, 4 vCPU; times are medians)

| What | Time | Size |
|---|---|---|
| Sync of 500 projects through the gateway (about 2,000 MCP calls) | 20 s | |
| Radar's nightly check of 500 projects | 0.7 s | |
| `portfolio.get_overview` | 195 ms | 646 KB JSON |
| `portfolio.list_projects` | 117 ms | 432 KB |
| `portfolio.get_project` | 40 ms | 2 KB |
| `portfolio.get_roadmap` | 150 ms | 530 KB |
| `portfolio.get_risks` | 74 ms | 161 KB |
| Overview page, in the browser (load event) | 1.2 s | 90 KB gzip (1.38 MB raw) |
| Projects page | 1.2–1.5 s | 57 KB gzip |
| Roadmap page | 0.9 s | 77 KB gzip |
| Risks page | 0.8 s | |

Tool times include the whole guard: token, rate limit, registry check, field projection, PII removal and
the audit row. Page times have no MCP cache (`MCP_CACHE_SECONDS=0`); in production the web app caches
read results for 60 seconds per user, so repeat visits are faster.

## What the test found and fixed

1. **The nightly sync was stopped by the gateway's own rate limit.** At 500 projects the sync makes
   about 2,000 calls; services shared the 120-per-minute limit meant for people. Services now get
   `SERVICE_RATE_LIMIT_PER_MINUTE` (6,000). Agents keep the limit set in Admin → Agents.
2. **Overview data took 407 ms.** It read 21,000 full snapshot rows. It now reads only the four
   columns it needs: 195 ms.
3. **One project's page read every project's history.** It now reads only that project's: 181 → 40 ms.
4. **Dependency lookups were a loop over all links for every project.** They now use an index.
5. **Tile notes listed every project** ("off track: A; B; C; …" for 60 projects). They now name three
   and say "and N more".
6. **Pages were sent uncompressed** (1.38 MB for the overview). The web app now gzips HTML, JSON and
   CSV responses: 90 KB.

## Not tested here

- Real tracker speed. JIRA Cloud and OpenProject answer in 100–500 ms per request, and the live
  connectors make 6–10 requests per project, so a live sync of 500 projects will take roughly
  10–30 minutes. That is fine for a nightly job at 02:00. Run the sync once against the real
  trackers to confirm.
- Many people at once. One gateway handled these calls one after another. For the Steering Committee
  and PMO (tens of users) this is far from a limit; run two gateway copies if that changes.
