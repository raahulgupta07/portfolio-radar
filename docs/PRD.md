# Digital Portfolio Tracker — PRD

Version 2 · 19 Oct 2026 · Owner: Rahul Gupta (City AI Team, City Holdings)

Version 2 adds what came out of the gap review and design work: the health rule,
the Radar agent, alerts, weekly digest, roadmap, risks, strategy alignment, and phone and iPad layouts.

## Overview

The Digital Portfolio Tracker is a read-only web app. It shows all City Holdings projects
and their progress in one view. It pulls data every day from the trackers each team already
uses: JIRA, OpenProject and Multica.

Today each team tracks work in its own tool. The CTO and the Steering Committee have no single
place to see all projects. People must ask each team or open each tool. This app solves that
without changing how teams work.

The front end starts from the prototype the CTO has given, restyled to the approved design
(`design/screens/`). An adapter (middleware) reads each tracker through its API and feeds the app.
One built-in agent, **Radar**, checks every project after each sync and tells people what needs them.

## Goals and non-goals

Goals:

1. One consistent view of all projects across JIRA, OpenProject and Multica.
2. Teams keep using their own tracker. No new data entry.
3. Data refreshes once a day, automatically.
4. The adapter has read-only access to every source. It never writes back.
5. Projects are matched by a standard project code prefix.
6. Radar finds problems early and tells the right person, with evidence.

Non-goals (what we will not do):

- Users cannot edit or update project status in the tracker. All data comes from the source tools.
- No real-time sync. Daily refresh only (a manual refresh by admin is allowed).
- No task management, sprint planning or time logging inside this app.
- No write-back to JIRA, OpenProject or Multica.
- Radar never sends a message without human approval.

## Users and roles

All users log in with City SSO. Nobody edits project data in the app.

| Role | Who | What they do | Source tracker |
| --- | --- | --- | --- |
| Viewer (executive) | CTO, Steering Committee | See the full portfolio, filter, drill into a project, read the digest | — |
| Viewer (team) | Digital Teams, Data Team, AI Team | See their own and other projects | — |
| Approver | PMO / Portfolio Admins group | Approve Radar's digests and nudges | — |
| Admin | Portfolio owner (IT) | Manage sources, prefixes, schedule, Radar rules, alerts | — |
| Data provider | Digital Teams | Update milestones, sprints, tasks in their tool | JIRA |
| Data provider | Data Team | Same | OpenProject |
| Data provider | AI Team and Agent Team | Same | Multica |

## Architecture

See `docs/architecture.md`. In short: adapter → database → API → web app, plus Radar reading the
database through read-only tools.

## Project code convention

Every project in every tracker must start its name with an approved prefix and a project code.
The adapter only picks up projects that match. The same code links a project across tools.

Format: `<PREFIX>-<PROJECT CODE>` then the project name.

| Prefix | Example |
| --- | --- |
| CHL-DP- | CHL-DP-PORTAL01 Customer Portal |
| CHL-IT- | CHL-IT-ERP02 ERP Upgrade |
| CHL-IT-DAAI- | CHL-IT-DAAI-GPT03 CityGPT Agents |
| CMHL-IT- | CMHL-IT-NET01 Network Refresh |

The prefix list is not fixed. Admins manage it in the app, so new prefixes need no code change.

Rules for the adapter:

- Match is case-insensitive. Store the code in upper case.
- Use the longest matching prefix (CHL-IT-DAAI- before CHL-IT-).
- Projects with no match are skipped and listed in a "non-compliant" report for admins.
- If two sources have the same code, show it as one project with two sources, and flag it.

## Screens

Approved designs are in `design/screens/`. Match layout, colours and copy.

| Screen | File | Notes |
| --- | --- | --- |
| Portfolio overview | `Main.dc.html` | Radar strip, health tiles, sources, trend, progress, milestones, project table with health and source filters |
| Radar (agent) | `Agent.dc.html` | One continuous conversation with Radar + Radar panel. Interactive |
| Roadmap | `Roadmap.dc.html` | Timeline Jul 2026–Jan 2027, milestones, today line, dependencies |
| Risks and strategy | `Risks.dc.html` | Risk matrix, risk register, 2030 aspiration alignment |
| Project detail | `Project.dc.html` | Health, progress, Radar note, milestones, sprint, trend, what changed, risks |
| Admin | `Admin.dc.html` | Sources, prefixes, schedule, Radar rules, alerts, non-compliant, sync log |
| Phone | `Phone-*.dc.html` | Radar, Overview, Project detail. Bottom tab bar |
| iPad | `iPad-*.dc.html` | Radar, Overview. Floating side menu |
| Radar character | `Radar-Moods.dc.html`, `RadarFace.dc.html`, `Radar-FaceOptions.dc.html` | Moods and face options |

Navigation: a floating menu on the left (desktop, iPad), centred vertically. Bottom tab bar on phone.

## Functional requirements

P1 = must have for first release. P2 = next release. P3 = later.

| ID | Requirement | Priority |
| --- | --- | --- |
| FR-01 | Login with City SSO (Microsoft Entra ID, OIDC). No local accounts. | P1 |
| FR-02 | Adapter connects to JIRA, OpenProject and Multica by API with read-only credentials. | P1 |
| FR-03 | Each source is a plug-in connector behind one common interface. | P1 |
| FR-04 | Adapter filters projects by the approved prefix list. | P1 |
| FR-05 | Adapter pulls per project: name, code, owner, team, status, start/end date, milestones, sprints (goal, dates), task counts by status, issue links (blocks), risk labels. | P1 |
| FR-06 | Adapter maps each source's fields to one common data model. | P1 |
| FR-07 | Scheduled sync once a day (default 02:00 Asia/Yangon). | P1 |
| FR-08 | Each sync is logged: start, end, source, projects read, errors. | P1 |
| FR-09 | If one source fails, keep its last good data and show a "Stale" badge with the last sync time. | P1 |
| FR-10 | Portfolio overview as designed (health tiles, sources, trend, progress, milestones, project table). | P1 |
| FR-11 | Filter by health, source, prefix, team, status. Search by code or name. | P1 |
| FR-12 | Project detail as designed, with "Edit in <source>" link (opens the source tool). | P1 |
| FR-13 | Summary tiles: on track, at risk, off track, done, each with change since last week. | P1 |
| FR-14 | No edit controls for project data. API has no write endpoints for project data. | P1 |
| FR-15 | Admin page as designed: sources, prefixes, schedule, manual sync, sync log, non-compliant list. | P1 |
| FR-16 | Export overview to Excel/CSV, project one-pager to PDF. | P2 |
| FR-17 | Health rule (On track / At risk / Off track / Done) — see "Health rule" below. | P1 |
| FR-18 | Daily snapshot per project for trends and "what changed". | P1 |
| FR-19 | Findings table: Radar's results per run, with type, severity, evidence, first seen. | P1 |
| FR-20 | Radar daily check after each sync (rules in `docs/radar-agent.md`). | P1 |
| FR-21 | Radar conversation screen: one continuous thread per user, with cards for findings, questions and approvals. | P1 |
| FR-22 | Weekly Steering Committee digest drafted by Radar; sent only after approval. | P2 |
| FR-23 | Nudges to project owners drafted by Radar; sent only after approval (Teams or email). | P2 |
| FR-24 | Radar answers questions in chat from the database, with evidence links. | P2 |
| FR-25 | Radar run log and approval log (who approved what, when). | P1 |
| FR-26 | Alerts: project turns Off track, milestone overdue, sync fails, digest ready. Channels: in app, email, Teams. | P2 |
| FR-27 | Roadmap screen: timeline of projects and milestones, today line, dependency list. | P2 |
| FR-28 | Dependencies read from tracker issue links plus PMO-recorded links. | P2 |
| FR-29 | Risk matrix and register, read from tracker risk labels/blockers and Radar findings. | P2 |
| FR-30 | Strategy tag per project (2030 aspiration), set in the tracker, shown on Risks and Overview. | P2 |
| FR-31 | Phone and iPad layouts as designed. | P2 |
| FR-32 | Radar face shows its current mood (see `docs/radar-agent.md`). | P2 |

## Health rule (proposal — confirm before build)

Computed every sync, in code, per project. Thresholds are admin settings (Admin → Radar).

- **Done**: source status is done.
- **Off track**: any milestone overdue by more than 3 days, or status "On hold" with an overdue milestone.
- **At risk**: progress is more than 15 points behind the share of time used (start→end), or
  the next milestone is within 7 days and the project is behind, or it waits for an Off-track project,
  or it has no owner / no milestone dates.
- **On track**: everything else.

## Data model

The adapter writes into these tables. The web app and Radar read from them, never from the sources.

| Table | Key fields |
| --- | --- |
| source | id, type (jira, openproject, multica), base_url, secret_ref, enabled, last_sync_at, last_status, last_error |
| prefix | id, value (e.g. CHL-DP-), description, active |
| project | id, code, prefix, name, team, owner, status, start_date, end_date, percent_done, health, strategy_tag, source_id, source_key, source_url, synced_at, source_updated_at |
| milestone | id, project_id, name, due_date, status, completed_at |
| sprint | id, project_id, name, goal, start_date, end_date, state |
| task_summary | project_id, todo, in_progress, done, total |
| dependency | id, from_project_id, to_project_id, kind (blocks), origin (tracker, pmo) |
| risk | id, project_id, title, likelihood, impact, owner, origin, review_date |
| snapshot | date, project_id, status, health, percent_done |
| sync_run | id, source_id, started_at, ended_at, projects_read, errors_json, result |
| non_compliant | id, source_id, name_in_tracker, reason, seen_at |
| finding | id, run_id, project_id, type (health, stale, data, slipping, sync, change), severity, text, evidence_json, first_seen_at, dismissed_by, dismissed_at |
| radar_message | id, user_id, kind (radar, me, ask, approval, pill), body, mood, payload_json, created_at |
| approval | id, kind (digest, nudge), draft_json, status (pending, approved, rejected), decided_by, decided_at, sent_at |
| radar_memory | id, text, created_by, created_at |
| agent_run | id, started_at, ended_at, projects_checked, findings, drafts |

Status mapping: each connector maps its own status values to: Not started, In progress, Done, On hold.
The mapping lives in config, not code.

## Non-functional requirements

- **Security:** source tokens in a secret store (e.g. Azure Key Vault), read-only scope. Never in code or DB.
- **Access:** every page and API needs SSO. Admin and approver actions need Entra ID groups.
- **Performance:** overview loads in under 3 seconds for 500 projects.
- **Sync:** full daily sync under 30 minutes. Respect rate limits with retry and back-off.
- **Reliability:** one failing source must not stop the others.
- **Audit:** keep sync, Radar run and approval logs for 90 days.
- **Accessibility:** WCAG 2.1 AA; real buttons/links; 44 px touch targets.
- **Deployment:** Docker. Config by environment variables. `docker compose up` runs everything locally.

## Build plan for Claude Code

Finish and test each phase before the next. Keep `docs/progress.md` up to date.

1. **Foundation:** repo, Docker Compose, PostgreSQL schema and migrations, seed from `design/sample-data.json`.
2. **Adapter:** connector interface + mock connector. Then JIRA, OpenProject, Multica (read-only). Prefix filter, field and status mapping, scheduler, sync log, stale handling.
3. **Health and snapshots:** health rule (FR-17), daily snapshots (FR-18), "what changed".
4. **Web app:** design tokens, floating menu, Overview, Project detail, Admin (match `design/screens/`).
5. **Auth:** City SSO, admin and approver roles.
6. **Radar phase 1 (Checker):** rule checks after sync, findings table, Radar conversation screen with findings and questions, run log.
7. **Radar phase 2 (Reporter):** weekly digest and nudges with approval flow; alerts.
8. **Radar phase 3 (Assistant):** chat answers with evidence; Teams channel.
9. **Roadmap, Risks, strategy tags.**
10. **Phone and iPad layouts.**
11. **Tests and README:** connector tests with recorded responses, prefix and health rule tests, end-to-end test of Overview and Radar approval.

Done means: all P1 items work, tests pass, and one real sync from each source shows correct data.

## Assumptions, risks and open questions

Main assumption: teams update milestones, sprint goals and task lists in their own tool on time.

| Risk | Effect | Mitigation |
| --- | --- | --- |
| Teams do not update their tool | Old or wrong progress | Show "last updated"; Radar flags no change in 14 days |
| Names break the code convention | Projects missing | Non-compliant report; share convention before go-live |
| Multica API limited or changes | AI Team projects missing | Confirm access early; isolated connector |
| Different status meanings per tool | Numbers not comparable | One status mapping and % done rule per tool |
| Radar says something wrong | Loss of trust | Rules-based checks, evidence on every answer, approval before sending |

Open questions:

- [ ] Which stack does the CTO prototype use? Where is its code?
- [ ] Are JIRA and OpenProject cloud or self-hosted? Can the adapter reach them?
- [ ] Does Multica have a public API, and who owns the access?
- [ ] Who is the portfolio owner (admin) and who approves Radar's messages?
- [ ] How is % done calculated: tasks done, milestones, or the tool's own field?
- [ ] Confirm the health rule thresholds above.
- [ ] Who keeps the official prefix list and strategy tags?
- [ ] Hosting: Azure or on-premise? Does Radar run on CityGPT or in this repo?
- [ ] Which Radar face option is final? (see `design/radar-face-options.png`)
