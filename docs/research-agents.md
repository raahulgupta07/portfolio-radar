# Gap review and AI agent research

19 Oct 2026 · background for the PRD. Not build instructions.

## Gaps found (now covered in PRD v2)

| Area | Gap | Where it is now |
| --- | --- | --- |
| Project health | No RAG rule | FR-17 health rule |
| Data quality | Only bad names checked | Radar checks |
| Alerts | None | FR-26 |
| Reports | Excel only | FR-22 weekly digest, FR-16 PDF one-pager |
| History and trends | Planned only | FR-18 snapshots |
| Timeline | None | FR-27 roadmap |
| Risks | None | FR-29 |
| Dependencies | None | FR-28 |
| Strategy alignment | None | FR-30 (2030 aspirations) |
| Resources, budget | None | Later (needs new data sources) |

## Always-on agents (September 2026)

| Agent | Who | What it is | What we reuse |
| --- | --- | --- | --- |
| [Meta Muse](https://www.techrepublic.com/article/news-meta-muse-ai-agent-us-launch/) | Meta, 8 Sep 2026 | Personal agent that keeps working after you leave and asks before sensitive actions | Background work, approval for sensitive actions, one continuous conversation |
| [OpenMuse](https://github.com/CopilotKit/openmuse/wiki) | CopilotKit, MIT, alpha | Open-source Muse: API, durable task worker, PostgreSQL; one review per outbound send | Durable task worker, one approval per outbound action |
| [OpenAI Dots](https://www.timesofai.com/news/openai-dots-ai-agents/) | OpenAI, 29 Sep 2026 | Always-on agents; read-only when working proactively; reachable in Teams | Read-only in background, "act vs ask" rules, Teams channel |
| [Open Dot](https://nerdschalk.com/open-dot-chatgpt-dots-alternative-mac/) | composio-community, Mac app | Open-source Dots: memory, skills, routines, event triggers; asks before send/post/change | Scheduled routines + event triggers, memory |

We copy the design, not the code: Open Dot lists no license, and OpenMuse is alpha and needs a
non-MIT CopilotKit service for chat history.

## Project management agents

| Agent | What it does |
| --- | --- |
| [Atlassian Rovo – Jira Delivery agent](https://support.atlassian.com/rovo/docs/work-with-jira-delivery-agent/) | Delivery health, stakeholder updates, stand-up digests, stale-work follow-up — JIRA only |
| [monday.com agents](https://monday.com/blog/ai-agents/how-project-management-teams-use-monday-ai-agents/) | Status Reporter, Dependency and Risk Mapper, Chief of Staff, capacity |
| [Taskade portfolio risk agent](https://www.taskade.com/agents/operations-intelligence/project-portfolio-risk-agent) | One health scale, mismatch of health vs risks, weekly digest |
| [Others (Asana, ClickUp, Wrike, Notion…)](https://resources.rework.com/tools/ai-agents/best-ai-agents-for-project-management-2026) | Status, risk, automation — inside one vendor's tool |

Our advantage: Radar sees JIRA, OpenProject and Multica together.
