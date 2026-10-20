# Portfolio Radar: City Holdings Digital Portfolio Tracker

A read-only portfolio tracker for City Holdings, with a built-in agent called **Radar**.

- Every night it reads projects from **JIRA, OpenProject and Multica**.
- It shows them in one place: overview, projects, roadmap, risks.
- Radar checks every project and tells people what needs attention.
- Radar drafts digests and nudges; **a named person approves them before anything is sent**.

Everything goes through one **City MCP Gateway**. The nightly sync, the web app, Radar, other City agents (CityGPT, Claude) and the notifier all use it. One guard checks every call, and one audit log records it.

![Overview](docs/images/overview.png)

| Sign in | Radar answers with evidence | Admin → People |
|---|---|---|
| ![Login](docs/images/login.png) | ![Radar](docs/images/radar.png) | ![People](docs/images/admin-people.png) |

**Contents:**

1. [How it works](#1-how-it-works)
2. [What is in the repository](#2-what-is-in-the-repository)
3. [Install](#3-install)
4. [First-time set-up (checklist)](#4-first-time-set-up-checklist)
5. [Sign-in: superadmin, City SSO, Keycloak and LDAP](#5-sign-in-superadmin-city-sso-keycloak-and-ldap)
6. [LLM for Radar (OpenRouter, CityGPT, Azure OpenAI)](#6-llm-for-radar)
7. [Configuration reference](#7-configuration-reference)
8. [Who can do what](#8-who-can-do-what)
9. [Running it: logs, backups, upgrades](#9-running-it-logs-backups-upgrades)
10. [Troubleshooting](#10-troubleshooting)
11. [Tests](#11-tests)
12. [Rules and more documents](#12-rules-and-more-documents)

---

## 1. How it works

### The parts

```mermaid
flowchart LR
  subgraph People
    U[Steering Committee<br/>PMO · teams · admins]
  end
  subgraph Agents
    A[CityGPT · Claude<br/>other City agents]
  end

  U -->|browser, HTTPS| W[Web app<br/>SvelteKit]
  W -->|MCP + the person's token| G
  A -->|MCP /omni + agent token| G
  K[Worker<br/>nightly sync · Radar · notifier] -->|MCP + service token| G

  subgraph G[City MCP Gateway · FastAPI]
    direction TB
    GU[Guard: token → caller → server limit → rate limit →<br/>tool on and approved → role → arguments →<br/>field projection → personal data removed → audit row]
    S1[/jira /openproject /multica<br/>read-only, GET only/]
    S2[/portfolio /radar /notify<br/>/admin /omni /system/]
  end

  G --> DB[(PostgreSQL<br/>app: portfolio data<br/>mcp: tools, audit, agents, people)]
  K -->|nightly adapter writes| DB
  S1 -->|HTTPS GET| T[JIRA · OpenProject · Multica]
  G -.-> SSO[City SSO<br/>Entra ID or Keycloak + LDAP]
  W -.-> SSO
  K -->|summaries, answers| L[LLM<br/>OpenRouter · CityGPT · Azure OpenAI]
  K -->|approved drafts only| N[Teams · email]
  G & K -.-> V[Secret store<br/>Key Vault in production]
```

| Part | Folder | What it does |
|---|---|---|
| City MCP Gateway | `backend/app/mcp/` | MCP servers. Inbound: `/jira`, `/openproject`, `/multica`. For callers: `/portfolio`, `/radar`, `/notify`, `/admin`, `/omni`, `/system`. Every call passes the guard. |
| Connectors | `backend/app/connectors/` | Read-only HTTP client (GET only). Live JIRA (Cloud and Data Center) and OpenProject; a mock that serves the sample data. |
| Nightly sync | `backend/app/adapter/` | Prefix rule, field and status mapping, stale sources, health rule (RAG), daily snapshots. |
| Radar | `backend/app/radar/` | Rule checks, morning message, questions to approvers, drafts, chat answers (rules, or the LLM with evidence), notifier. |
| Worker | `backend/app/worker.py` | Runs the nightly sync and Radar's check; answers chat; sends approved drafts. |
| Web app | `web/` | The screens, plus PDF one-pagers and CSV export. It talks only to the gateway (MCP), never to the database. |
| Programs | `backend/app/portfolio/programs.py`, `web/src/routes/programs/` | Read-only program office view: charters, budget, RACI, next steps. Load the file with `python -m app.adapter po-import <file>`, then turn on `portfolio.get_programs` in Admin → MCP tools. |
| Teams chat | `backend/app/teams/`, `teams/` | 1:1 chat with Radar in Microsoft Teams, through the gateway. |
| Azure | `infra/`, `.github/workflows/` | Bicep: Container Apps, private PostgreSQL, Key Vaults, managed identities. CI and deploy workflows. |

### One request, step by step

```mermaid
sequenceDiagram
  participant B as Browser
  participant W as Web app (server)
  participant G as Gateway guard
  participant T as Tool (e.g. portfolio.get_overview)
  participant D as PostgreSQL
  B->>W: GET / (session cookie)
  W->>G: MCP tools/call + person's token
  G->>G: token valid? (SSO, superadmin or dev)<br/>blocked in Admin → People?
  G->>G: rate limit · tool on and approved · role · inputs
  G->>T: run
  T->>D: read
  D-->>T: rows
  T-->>G: result
  G->>G: keep only asked-for fields · remove personal data
  G->>D: audit row (who, tool, result, time)
  G-->>W: result
  W-->>B: page (gzip, CSP)
```

### Every night

```mermaid
flowchart LR
  C[02:00 Asia/Yangon<br/>time set in Admin] --> S[Sync: read every tracker<br/>through /jira /openproject /multica]
  S --> P{Name starts with an<br/>approved prefix?}
  P -- no --> NC[Listed as badly named]
  P -- yes --> M[Map fields and status<br/>nothing is guessed]
  M --> H[Health rule: on track / at risk /<br/>off track / done] --> SN[Daily snapshot]
  SN --> R[Radar checks every project] --> F[Findings, questions,<br/>draft digest]
  F --> A{A named approver<br/>says yes?}
  A -- yes --> N[Notifier sends:<br/>Teams · email]
  A -- no --> X[Nothing is sent]
```

A source that fails keeps its last good data and is shown as **stale**; the other sources still sync.

---

## 2. What is in the repository

```
backend/            Python 3.12: gateway, connectors, nightly sync, Radar, worker
  app/mcp/          the gateway: guard, identity, registry, MCP servers
  app/connectors/   JIRA, OpenProject, mock; read-only HTTP client
  alembic/          database migrations (run on gateway start)
  tests/            pytest (needs PostgreSQL)
web/                SvelteKit 2 + Svelte 5 + Tailwind 4: the screens
  e2e/              Playwright browser tests
design/             approved screen designs and sample data
docs/               architecture, deploy, SSO, security review, load test
infra/              Azure Bicep; infra/sso-dev = Keycloak + LDAP demo
teams/              Teams app package (manifest, icons)
docker-compose.yml       the whole app on one machine
docker-compose.sso.yml   adds Keycloak with a sample LDAP directory
```

---

## 3. Install

Pick one:

| Option | For | Time |
|---|---|---|
| [A. Docker on one machine](#a-docker-on-one-machine) | Trying it, a test server, a small on-premise install | 10 min |
| [B. Docker with Keycloak + LDAP](#b-docker-with-keycloak-and-ldap) | Trying real sign-in against a directory | 15 min |
| [C. Azure](#c-azure-production) | Production | 1–2 h, mostly app registrations |
| [D. Without Docker](#d-without-docker-developers) | Working on the code | 15 min |

### Requirements

- **Options A and B:** Docker 24+ with Compose v2 (`docker compose version`), 4 GB RAM, ports 3000 and 8000 free (8081 for option B).
- **Option C:** an Azure subscription, rights to create app registrations in Entra ID (or a Keycloak realm), and this repository on GitHub.
- **Option D:** Python 3.12+, Node 22, PostgreSQL 16.

### A. Docker on one machine

```bash
git clone https://github.com/raahulgupta07/portfolio-radar.git
cd portfolio-radar

# 1. Your own settings (this file is not in git). At least a superadmin:
cat > backend/.env <<'EOF'
SUPERADMIN_USERNAME=superadmin
SUPERADMIN_PASSWORD=choose-a-long-password-here
EOF

# 2. Start database, gateway, worker and web app
docker compose up --build -d
docker compose ps                       # all four "Up"; db and mcp "healthy"

# 3. Load the sample data (10 projects, history, Radar's first check). Skip this for real data.
docker compose exec mcp python -m app.adapter demo
```

Open **http://localhost:3000** (use `localhost`, not `127.0.0.1`):

- **Superadmin sign-in**: the name and password from step 1, or
- **Development sign-in**: sample Viewer, PMO Approver or Admin (`DEV_LOGIN=true` in this mode only).

The gateway is at http://localhost:8000: `/healthz`, `/readyz`, and `/<server>/mcp` with a bearer token. Both ports listen on this machine only. To reach the app from other machines, put a reverse proxy with HTTPS in front of port 3000 and set `ORIGIN` (see [Configuration](#7-configuration-reference)).

> This mode runs with `APP_ENV=dev`: sample users and dev tokens work. **For a real install**, set `APP_ENV=prod`, `DEV_LOGIN=false`, a superadmin **hash**, and City SSO. Section 5 explains each.

### B. Docker with Keycloak and LDAP

The same as A, plus Keycloak, and an OpenLDAP directory with three sample users:

```bash
docker compose -f docker-compose.yml -f docker-compose.sso.yml up --build -d
docker compose exec mcp python -m app.adapter demo
```

Open http://localhost:3000 → **Sign in with City SSO** → the Keycloak page:

| User | Password | LDAP groups | Role in the app |
|---|---|---|---|
| `min` | `viewer-pass` | portfolio-viewers | viewer |
| `aye` | `approver-pass` | + portfolio-approvers | approver |
| `rahul` | `admin-pass` | + portfolio-admins | admin |

The Keycloak console is at http://localhost:8081 (`admin` / `dev-keycloak-admin`). These are demo passwords; use your own directory for real. Details: [`docs/sso.md`](docs/sso.md).

### C. Azure (production)

```mermaid
flowchart LR
  GH[GitHub Actions<br/>OIDC, no stored Azure password] -->|Bicep| RG
  subgraph RG[Resource group]
    WEB[ca-radar-web<br/>public HTTPS] --> MCP[ca-radar-mcp<br/>internal HTTPS]
    WRK[ca-radar-worker] --> MCP
    MCP --> PG[(PostgreSQL<br/>private)]
    WRK --> PG
    MCP & WRK & WEB --> KV[Key Vaults<br/>private endpoints]
    ACR[Container Registry]
  end
```

1. App registrations (Entra ID) or a Keycloak realm. See [`docs/deploy-azure.md`](docs/deploy-azure.md) step 1 or [`docs/sso.md`](docs/sso.md).
2. Create a resource group and an identity that GitHub Actions can sign in as ([`docs/deploy-azure.md`](docs/deploy-azure.md) step 2).
3. In GitHub, create the `production` environment and set its variables and secrets. Include `SUPERADMIN_USERNAME` (variable) and `SUPERADMIN_PASSWORD_HASH` (secret) if you want a superadmin.
4. **Actions → Deploy to Azure → Run workflow.** It creates everything, builds the images, deploys, and checks `/healthz`.
5. First start: turn the tools on, then follow [section 4](#4-first-time-set-up-checklist).

Full guide: [`docs/deploy-azure.md`](docs/deploy-azure.md).

### D. Without Docker (developers)

```bash
# gateway
cd backend
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env              # then edit .env
alembic upgrade head
uvicorn app.main:app --port 8000

# sample data (dev only), in another terminal
python -m app.adapter demo

# worker
python -m app.worker

# web app
cd ../web && npm install && cp .env.example .env && npm run dev   # http://localhost:5173
```

---

## 4. First-time set-up (checklist)

Signed in as the **superadmin** (or an admin):

- [ ] **Turn the tools on.** New MCP tools start **off**, and a tool whose code changes waits for review (Admin → MCP tools). From the command line:
  ```bash
  docker compose exec mcp python -m app.mcp.cli tools
  for s in portfolio radar notify admin omni system jira openproject; do
    docker compose exec mcp python -m app.mcp.cli on "$s.*" --by "Your Name"; done
  ```
  The `demo` command does this for you.
- [ ] **City SSO**: Admin → Connections → *Sign-in, LLM and sending* → **City SSO**. Choose Entra ID or Keycloak/LDAP, map groups to roles, then **Check**. Set the web app's sign-in settings too (section 5).
- [ ] **Trackers**: Admin → Connections → JIRA / OpenProject:
  1. Address, service account, and the read-only token (pasted once; it goes to the secret store).
  2. **Run the check.**
  3. Fill in and **confirm the field mapping**: where your tracker keeps status, dates, owner, % done and the 2030 tag.
  4. The **status mapping**.
  5. Set `SOURCE_MODE=live` and restart.
- [ ] **Prefixes**: Admin → Settings. Only projects whose names start with an approved prefix are tracked (for example `CHL-IT-DAAI-`).
- [ ] **LLM** (optional): section 6. Without one, Radar answers from rules, with evidence.
- [ ] **Teams and email** (optional): webhook, chat bot, SMTP. Each has a test button.
- [ ] **People**: Admin → People. Check who signed in; add exceptions.
- [ ] **Sync time**: Admin → Settings (default 02:00 Asia/Yangon).
- [ ] **Superadmin**: keep it as a break-glass account (long password, stored as a hash), or remove `SUPERADMIN_USERNAME` once SSO works.

---

## 5. Sign-in: superadmin, City SSO, Keycloak and LDAP

The app keeps **no user passwords**, with one exception: the optional superadmin.

```mermaid
flowchart TB
  L[Login page] --> S1[Sign in with City SSO]
  L --> S2[Superadmin sign-in]
  L -.dev only.-> S3[Sample users]
  S1 --> E[Microsoft Entra ID]
  S1 --> KC[Keycloak] --> LD[(LDAP / Active Directory)]
  E & KC -->|access token with groups| GW[Gateway]
  S2 -->|name + password| GW
  GW -->|groups → roles<br/>+ Admin → People rules| R[viewer / approver / admin]
```

### Superadmin (local account)

One account with a name and password, for **setting the app up before SSO works** and as a **break-glass** way in when SSO is down.

| | |
|---|---|
| Roles | viewer + admin. **Never approver**: approvals stay with named people |
| Password | Stored as an scrypt hash. In production only the hash is accepted |
| Session | 60 minutes (`SUPERADMIN_SESSION_MINUTES`); a new password ends every session |
| Lock-out | 5 wrong tries from one address, or 20 in all → 15 minutes' wait |
| Audit | Every try is in Admin → Activity (`auth.local_sign_in`); the password never is |
| Off | Leave `SUPERADMIN_USERNAME` empty |

**Set it up for production:**

```bash
# 1. Make the hash. It asks for the password twice and prints scrypt:...
docker compose exec mcp python -m app.localadmin hash        # or: cd backend && python -m app.localadmin hash

# 2. Put it in backend/.env (Docker) or the GitHub secret SUPERADMIN_PASSWORD_HASH (Azure)
SUPERADMIN_USERNAME=superadmin
SUPERADMIN_PASSWORD_HASH=scrypt:16384:8:1:...

# 3. Restart the gateway
docker compose up -d mcp
```

In development, `SUPERADMIN_PASSWORD=...` (plain text) also works. With `APP_ENV=prod` it is refused.

### City SSO with Microsoft Entra ID

| Where | Settings |
|---|---|
| Web app (`web/.env`) | `ENTRA_TENANT_ID`, `ENTRA_CLIENT_ID`, `ENTRA_CLIENT_SECRET`, `ENTRA_API_SCOPE` |
| Gateway | Admin → Connections → City SSO: provider Entra ID, tenant, audience, groups → roles. Or `ENTRA_TENANT_ID`, `ENTRA_AUDIENCE`, `ENTRA_USER_APPS`, `ENTRA_GROUP_ROLES` |

The app registrations are described in [`docs/deploy-azure.md`](docs/deploy-azure.md) step 1.

### City SSO with Keycloak (and LDAP or Active Directory)

Keycloak checks the password against LDAP (User Federation) and puts the person's groups in the token, so the app never sees a password.

| Where | Settings |
|---|---|
| Web app (`web/.env`) | `OIDC_ISSUER=https://sso.city.local/realms/city`, `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET`, optional `SSO_LABEL` |
| Gateway | Admin → Connections → City SSO: provider Keycloak/LDAP, realm address, audience, sign-in client, groups → roles. Or `SSO_PROVIDER=keycloak`, `OIDC_ISSUER`, `ENTRA_AUDIENCE`, `ENTRA_USER_APPS`, `ENTRA_GROUP_ROLES` |

Keycloak needs an audience mapper and a group-membership mapper on the web client. `infra/sso-dev/realm-city.json` is a working example. Step-by-step: [`docs/sso.md`](docs/sso.md).

### Admin → People

- See everyone who signed in, with their roles from groups and their last sign-in.
- **Add a role** for one person, with a note.
- **Add someone** before their first sign-in.
- **Block** a person.

Changes apply on the person's next call. To give a whole team a role, map their group instead.

---

## 6. LLM for Radar

Radar's health checks are always plain rules. An LLM only writes summaries and answers questions, and every answer shows its evidence (the MCP calls that ran). With no LLM set, Radar answers from rules.

Any **OpenAI-compatible** endpoint works: OpenRouter, CityGPT, Azure OpenAI, or a proxy. Set it in **Admin → Connections → LLM for Radar**, where the key goes to the secret store. Or set it in env; once saved, the Admin values win.

### OpenRouter

```bash
# backend/.env  (Docker)   — or the same names in your platform's settings
LLM_PROVIDER=openrouter
LLM_API_KEY=sk-or-v1-...          # from openrouter.ai → Keys
LLM_MODEL=vendor/model-name       # any id listed on openrouter.ai/models
# LLM_BASE_URL is set to https://openrouter.ai/api/v1 for you
LLM_APP_URL=https://portfolio.cityholdings.com.mm   # optional, shown in OpenRouter's dashboard
```

```bash
docker compose up -d mcp worker   # pick up the change
```

Or in Admin: provider **OpenRouter**, leave the address empty, enter the model id, paste the key, **Test with one question**.

The worker uses the LLM (answers and digests); the gateway uses it only for the test button. With Docker, both read `backend/.env`. On Azure, set it in Admin, so the key goes to Key Vault.

### Others

| Provider | `LLM_BASE_URL` | `LLM_MODEL` |
|---|---|---|
| CityGPT | your CityGPT `/v1` address | its model name |
| Azure OpenAI | `https://<resource>.openai.azure.com/openai/v1` | your deployment name |
| Claude via a gateway | the gateway's OpenAI-compatible `/v1` address | its model name |

Addresses must be **https**. Tracker text goes to the LLM as data, never as instructions. The LLM's tools are read-only.

---

## 7. Configuration reference

Values come from environment variables, from `backend/.env` and `web/.env`, or, for most connection settings, from **Admin** (Admin wins). Lists and maps are JSON. Never commit real secrets: use the secret store (Admin) or your platform's secret settings.

### Gateway and worker (`backend/.env`)

| Variable | Default | What |
|---|---|---|
| `APP_ENV` | `prod` | `dev` / `test` / `prod`. Dev tokens and sample users work only in dev/test |
| `DATABASE_URL` | local | `postgresql+psycopg://user:pass@host:5432/radar` |
| `SOURCE_MODE` | `mock` | `mock` = sample data; `live` = the trackers set up in Admin |
| `TIMEZONE` | `Asia/Yangon` | For the nightly schedule and "today" |
| **Superadmin** | | |
| `SUPERADMIN_USERNAME` | empty (off) | The superadmin's name |
| `SUPERADMIN_PASSWORD_HASH` | | From `python -m app.localadmin hash` (production) |
| `SUPERADMIN_PASSWORD` | | Plain text, dev only |
| `SUPERADMIN_SESSION_MINUTES` | `60` | Session length |
| **City SSO** (or set in Admin) | | |
| `SSO_PROVIDER` | `entra` | `entra` or `keycloak` |
| `ENTRA_TENANT_ID` | | Entra tenant |
| `OIDC_ISSUER` | | Keycloak realm address |
| `OIDC_INTERNAL_ISSUER` | | Where the gateway reaches Keycloak, if not at the issuer address (Docker) |
| `ENTRA_AUDIENCE` | | The gateway's audience (both providers) |
| `ENTRA_USER_APPS` | `[]` | Client IDs people sign in through. **Required in production** |
| `ENTRA_GROUP_ROLES` | `{}` | `{"<group>": ["viewer","approver"]}` |
| `ENTRA_DEFAULT_ROLES` | `["viewer"]` | Roles for everyone who signs in; `[]` = only mapped groups |
| `ENTRA_APPS` | `{}` | Apps signing in as themselves: `{"<client id>": {"kind":"service","id":"adapter","roles":["adapter"]}}` |
| **LLM** (or set in Admin) | | |
| `LLM_PROVIDER` | `citygpt` | `citygpt`, `azure_openai`, `claude`, `openrouter`, `other` |
| `LLM_BASE_URL` | empty | OpenAI-compatible `/v1` address (OpenRouter: filled in) |
| `LLM_API_KEY` | | The key |
| `LLM_MODEL` | | Model id |
| `LLM_APP_URL` | | OpenRouter only: your app's address |
| **Sending** (or set in Admin) | | |
| `TEAMS_WEBHOOK_URL` | | Incoming webhook for approved drafts |
| `TEAMS_BOT_APP_ID`, `TEAMS_BOT_PASSWORD` | | Teams chat with Radar ([`docs/teams-bot.md`](docs/teams-bot.md)) |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`, `NOTIFY_EMAIL_TO` | | Email |
| **Secrets** | | |
| `SECRET_STORE` | `local` | `local` (a file, dev only) or `keyvault` |
| `KEY_VAULT_URL` | | `https://<vault>.vault.azure.net/` |
| **Worker sign-in** | | |
| `GATEWAY_URL` | `http://localhost:8000` | How the worker reaches the gateway |
| `SERVICE_AUTH` | `token` | `token` (dev tokens) or `managed_identity` (Azure) |
| `GATEWAY_SCOPE`, `ADAPTER_CLIENT_ID`, `RADAR_JOB_CLIENT_ID`, `RADAR_AGENT_CLIENT_ID`, `NOTIFIER_CLIENT_ID` | | Azure managed identities, one per job |
| **Gateway** | | |
| `MCP_ALLOWED_HOSTS`, `MCP_ALLOWED_ORIGINS` | localhost | Host and Origin headers the gateway accepts (DNS-rebinding protection) |
| `RATE_LIMIT_PER_MINUTE` | `120` | Per person or agent |
| `SERVICE_RATE_LIMIT_PER_MINUTE` | `6000` | Per service (the sync makes about 4 calls per project) |
| `DEV_TOKENS` | `{}` | Dev only: fixed tokens for sample users and services |

### Web app (`web/.env`)

| Variable | What |
|---|---|
| `ORIGIN` | The address people use, e.g. `https://portfolio.cityholdings.com.mm`. **Must match**, or forms are refused |
| `GATEWAY_URL` | How the web server reaches the gateway |
| `MCP_CACHE_SECONDS` | Read cache per person (default 60) |
| `OIDC_ISSUER`, `OIDC_INTERNAL_ISSUER`, `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET`, `OIDC_SCOPE`, `SSO_LABEL` | Keycloak sign-in |
| `ENTRA_TENANT_ID`, `ENTRA_CLIENT_ID`, `ENTRA_CLIENT_SECRET`, `ENTRA_API_SCOPE` | Entra ID sign-in |
| `DEV_LOGIN`, `DEV_USERS` | Sample users. `DEV_LOGIN=false` in production |
| `MCP_PUBLIC_URL` | The gateway address shown to agents in Admin → Agents |

---

## 8. Who can do what

| Caller | Examples | Can |
|---|---|---|
| Person, **viewer** | CTO, Steering Committee, teams | Read the portfolio, PDFs and CSV; talk to Radar |
| Person, **approver** | PMO | Also answer Radar's questions; approve, edit or reject drafts |
| Person, **admin** | Portfolio owner (IT) | Also Admin: connections, tools, people, agents, settings, activity |
| **Superadmin** | IT, during set-up | Viewer + admin. Not approver |
| **Agent** | Radar chat, CityGPT, Claude (`/omni`) | Read the portfolio, draft. Never approve or send |
| **Service** | adapter, radar-job, notifier, teams | Read trackers; post findings and drafts; send approved drafts; pass Teams questions to Radar |

Hard rules, enforced in code:

- **Read-only to the trackers**: the HTTP client has no write methods.
- **No edit controls** for project data anywhere in the app.
- **Nothing is sent without a named approver.**
- **Health comes from rules, not the LLM.**

---

## 9. Running it: logs, backups, upgrades

| Task | Docker | Azure |
|---|---|---|
| Health | `curl localhost:8000/readyz` · `localhost:3000/healthz` | the same paths, through Container Apps probes |
| Logs | `docker compose logs -f mcp worker web` | Log Analytics (90 days) |
| Who did what | Admin → Activity, or `python -m app.mcp.cli calls` | same |
| Sync now | `docker compose exec mcp python -m app.adapter sync --in-process` | Admin → Settings → Sync now |
| Backup | `docker compose exec db pg_dump -U radar radar > radar-$(date +%F).sql` | PostgreSQL point-in-time restore (14 days) |
| Restore | `cat file.sql \| docker compose exec -T db psql -U radar radar` | Azure portal → Restore |
| Upgrade | `git pull && docker compose up --build -d` (migrations run on start) | push to `main`, or run the deploy workflow |
| Tool changes after an upgrade | Admin → MCP tools → *Review* (changed tools wait for an owner) | same |
| Rotate a tracker token | Admin → Connections → the source → paste a new token | same |

Keep `backend/.env`, `web/.env` and the `devsecrets` Docker volume out of git and out of shared drives. In production, use Key Vault (`SECRET_STORE=keyvault`).

---

## 10. Troubleshooting

| You see | Why | Fix |
|---|---|---|
| "Cross-site POST form submissions are forbidden" | The address in the browser is not `ORIGIN` | Open the app at `ORIGIN` (e.g. `localhost`, not `127.0.0.1`), or set `ORIGIN` to the address people use |
| Login page has no superadmin form | `SUPERADMIN_USERNAME` or the password is missing, or the web app cannot reach the gateway | Set both, then `docker compose up -d mcp` |
| "Wrong name or password" even when right | Locked after 5 wrong tries | Wait 15 minutes; check Admin → Activity |
| "Your City account cannot use Portfolio Radar" | Blocked in Admin → People, or no group gives a role | Unblock, map the group, or tick "Everyone who signs in is a viewer" |
| SSO: "Token rejected: wrong issuer" | The realm or tenant in Admin differs from the token | For Keycloak, the realm address must be exactly what people's browsers use |
| SSO: "people sign in through the Portfolio Radar app only" | The web client ID is not listed | Add it to *Sign-in apps* (`ENTRA_USER_APPS`) |
| A page says a tool is off | New or changed tools start off | Admin → MCP tools → turn on or approve |
| A source is "stale" | Its last sync failed | Admin → Connections → the source → Run the check; read the error |
| "field mapping not confirmed yet" | Live sync waits for a person | Admin → Connections → the source → Field mapping → tick and save |
| "status '…' has no mapping" | A tracker status the app does not know | Admin → Connections → the source → Status mapping |
| Radar answers "from rules" | No LLM set, or the test failed | Section 6; use **Test with one question** |
| `docker compose up` fails with 429 | Docker Hub download limit | Wait a few minutes, or `docker login` |

---

## 11. Tests

```bash
cd backend && . .venv/bin/activate && pytest                          # 140+ tests; needs a radar_test database
cd web && npm run check                                               # types
cd web && E2E_BASE_URL=http://localhost:3000 npx playwright test app  # browser tests against a running stack
cd web && E2E_SSO=1 E2E_BASE_URL=http://localhost:3000 npx playwright test sso   # against option B
```

CI (`.github/workflows/ci.yml`) runs the backend tests on PostgreSQL, the type check and build, and a Bicep lint on every push.

---

## 12. Rules and more documents

| Document | What |
|---|---|
| [`docs/architecture.md`](docs/architecture.md) | How the parts fit, servers and tools, daily flow |
| [`docs/deploy-azure.md`](docs/deploy-azure.md) | Azure, step by step |
| [`docs/sso.md`](docs/sso.md) | Entra ID, Keycloak, LDAP, People |
| [`docs/teams-bot.md`](docs/teams-bot.md) | Chat with Radar in Teams |
| [`docs/security-review.md`](docs/security-review.md) | What was checked and fixed |
| [`docs/load-test.md`](docs/load-test.md) | 500 projects: results |
| [`docs/PRD.md`](docs/PRD.md) · [`docs/radar-agent.md`](docs/radar-agent.md) | Requirements · Radar |
| [`docs/progress.md`](docs/progress.md) | Build log and open questions |
| [`CLAUDE.md`](CLAUDE.md) | Rules for anyone changing the code |
