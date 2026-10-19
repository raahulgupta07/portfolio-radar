# Digital Portfolio Tracker

Read-only portfolio tracker for City Holdings, with the built-in agent **Radar**.

This repo starts as a **hand-off kit** for Claude Code: requirements, architecture,
agent spec and approved designs. Code is built from these files.

## Folder map

| Path | What it is |
| --- | --- |
| `CLAUDE.md` | Rules and reading order for Claude Code. Read first. |
| `docs/PRD.md` | Product requirements, data model, build plan, open questions |
| `docs/architecture.md` | System architecture and data flow |
| `docs/radar-agent.md` | Radar agent: checks, routines, tools, approvals, moods |
| `docs/design-system.md` | Colours, fonts, radii, components, layout rules |
| `docs/research-agents.md` | Gap review and market research on AI agents |
| `design/screens/` | Approved screen designs (desktop, phone, iPad) as HTML |
| `design/sample-data.json` | Sample projects used in the designs and for mock connectors |
| `design/radar-face-options.png` | Face options for Radar (pick one) |

## Start with Claude Code

```bash
cd portfolio-tracker
git init && git add . && git commit -m "Hand-off kit: PRD, architecture, Radar spec, designs"
claude
```

First prompt to give Claude Code:

> Read CLAUDE.md and every file it lists. Then write a build plan for Phase 1 in
> docs/progress.md, list any open questions, and wait for my OK before writing code.

Then go phase by phase:

> Build Phase 1 from docs/progress.md. Use mock connectors with design/sample-data.json.
> Match the screens in design/screens/. Run the tests when done.
