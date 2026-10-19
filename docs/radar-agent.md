# Radar — the portfolio agent

Radar is the only agent in the app. It watches every project in JIRA, OpenProject and Multica,
and tells people only what needs them. One continuous conversation per user (like Meta Muse),
not many threads.

## What Radar does

| Ability | When | Output |
| --- | --- | --- |
| Health check | Daily, right after the sync | Health per project, findings |
| Data quality | Daily | Findings: no owner, no milestone dates, no sprint goal, bad names |
| Sync watch | On every sync | Finding + alert when a source fails; marks data stale |
| Stale work check | Monday 09:00 | Findings for projects with no update in 14 days |
| Weekly digest | Friday 16:00 (draft ready earlier) | Steering Committee digest — needs approval |
| Nudges | When a project stays Off track | Message draft to the owner — needs approval |
| Answer questions | Any time | Chat answer with evidence (source, project code, sync time) |

## Checks (code rules, not LLM)

- **Off track:** milestone overdue > 3 days (setting), or On hold with an overdue milestone.
- **At risk:** progress behind time used by > 15 pts (setting); next milestone within 7 days and behind; waits for an Off-track project; no owner; no milestone dates.
- **Stale:** no change in the source for 14 days (setting).
- **Sync:** source failed; project disappeared; non-compliant name.
- **Change:** health, status, dates or progress changed since last week (from snapshots).

Each finding stores: type, severity, project, text, evidence (source, fields, sync time), first seen date.
Radar remembers findings so it can say "red for 1 week" and does not repeat the same alert.

## Conversation model

One thread per user, stored in `radar_message`. Message kinds:

| Kind | Looks like | Example |
| --- | --- | --- |
| `radar` | Radar bubble, optional evidence line | "Good morning Rahul. I checked 10 projects. 4 things need you." |
| `me` | User bubble | "Why is Loyalty App at risk?" |
| `ask` | Yellow "RADAR ASKS" card with buttons | "Should I draft a nudge to the POS03 owner?" Yes / Not now |
| `approval` | Black card: title, recipients, draft, Approve / Edit / Reject | Weekly digest, nudge |
| `health`, `findings`, `dep` | Rich cards | Health tiles, finding cards, dependency card |
| `pill` | Grey system line | Call summary, "Still waiting for your answer…" |

A "Waiting for you" bar above the chat lists open questions and pending approvals.
If a question is not answered, Radar posts one reminder, then asks again two days later.

## Tools (read-only + drafts)

- `list_projects(filter)`, `get_project(code)`, `get_history(code, weeks)`
- `get_findings(run_id | today)`, `get_dependencies(code)`, `get_risks(code)`
- `get_sync_status()`
- `create_draft(kind, recipients, body)` — creates an approval item, never sends
- `remember(text)` / `forget(id)` — Radar memory, visible and editable in the Radar panel

No tool can write to the source trackers. Sending is done by the Notifier after approval.

## Rules

1. Reads only. Never changes JIRA, OpenProject or Multica.
2. Asks before it sends any message.
3. Shows the evidence behind every answer.
4. If data is stale, says so in the answer.
5. Plain, short, international English.

## Moods (face)

The face shows what Radar is doing. Component: `design/screens/RadarFace.dc.html` (prop `mood`).

| Mood | When | Status text |
| --- | --- | --- |
| ready | Free, waiting | Ready · read-only |
| resting | Between jobs, at night | Resting · next check 02:10 |
| scanning | During the nightly check | Checking 6 of 10 projects… |
| thinking | Writing an answer or digest | Writing the digest… |
| alert | A project turns red / milestone late | 4 things need you |
| asking | Waiting for answer or approval | Waiting for you |
| happy | Approved, or all on track | All done · digest scheduled |
| listening | On a call | Listening… |
| offline | A source sync failed | Can't reach Multica |

Header mood priority: listening > scanning > asking (open items) > alert (new red findings) > offline > happy > ready.

Final face design: pick from `design/radar-face-options.png` (Dish, Owl, Ghost, Lighthouse, Orbit) or keep the current mint face.
