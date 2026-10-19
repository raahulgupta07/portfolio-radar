"""Radar's words. Rules decide what matters; this module only phrases it.

With an LLM set up (LLM_BASE_URL, LLM_MODEL), the morning summary and digest
are polished by the LLM from the facts given, with a strict instruction not
to add facts. Without one, plain templates are used. Either way the facts and
the evidence come from the rule checks, never from the LLM.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

from app.settings import Settings

log = logging.getLogger("radar.writer")

STYLE = ("Write in plain, simple international English. Short sentences, everyday words. "
         "Use only the facts given. Do not add numbers, names or dates that are not in the facts. "
         "Keep project codes exactly as given.")


def llm_ready(settings: Settings) -> bool:
    return bool(settings.llm_base_url and settings.llm_model)


async def polish(settings: Settings, task: str, facts: str, fallback: str) -> str:
    """Ask the LLM to phrase `facts`. Falls back to the template on any error."""
    if not llm_ready(settings):
        return fallback
    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(base_url=settings.llm_base_url, api_key=settings.llm_api_key or "none", timeout=60)
        r = await client.chat.completions.create(
            model=settings.llm_model, temperature=0.2,
            messages=[{"role": "system", "content": f"You are Radar, City Holdings' portfolio agent. {STYLE}"},
                      {"role": "user", "content": f"{task}\n\nFacts:\n{facts}"}])
        text = (r.choices[0].message.content or "").strip()
        return text or fallback
    except Exception as e:  # noqa: BLE001  never let wording break the job
        log.warning("LLM failed, using template: %s", type(e).__name__)
        return fallback


def plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def morning_text(projects: int, findings: list[dict[str, Any]], sources: list[dict[str, Any]]) -> str:
    n = len(findings)
    first = f"Good morning. I checked {plural(projects, 'project')} after the daily sync."
    if not n:
        return f"{first} Nothing needs you today. All checks passed."
    high = [f for f in findings if f["severity"] == "high"]
    lines = [f"{first} {plural(n, 'thing')} need{'s' if n == 1 else ''} you."]
    if high:
        lines.append("Most urgent: " + "; ".join(f["text"] for f in high[:2]) + ".")
    stale = [s["name"] for s in sources if s.get("stale")]
    if stale:
        lines.append(f"{', '.join(stale)} could not be read, so I used its last good data.")
    return "\n".join(lines)


def evidence_line(sources: list[dict[str, Any]], fmt) -> str:
    parts = []
    for s in sources:
        if s.get("stale"):
            parts.append(f"{s['name']} data from {fmt(s.get('last_good_sync_at'))}")
        else:
            parts.append(f"{s['name']} synced {fmt(s.get('last_sync_at'))}")
    return "; ".join(parts)


def nudge_text(p: dict[str, Any], reasons: list[str]) -> str:
    owner = p.get("owner") or "project owner"
    why = " ".join(r.rstrip(".") + "." for r in reasons) if reasons else "It is off track."
    return (f"Hello {owner},\n\n{p['name']} ({p['code']}) is off track in the portfolio tracker. {why}\n\n"
            f"Could you update {p['source_name']} with the new plan, or tell the PMO what help you need?\n"
            f"Edit here: {p.get('source_url') or p['source_name']}\n\nThank you.")


def digest_text(today: date, tiles: list[dict[str, Any]], findings: list[dict[str, Any]],
                projects: list[dict[str, Any]], sources: list[dict[str, Any]]) -> str:
    """Steering Committee digest. Decisions first (docs/radar-agent.md)."""
    off = [p for p in projects if p.get("health") == "off_track"]
    risk = [p for p in projects if p.get("health") == "at_risk"]
    lines = [f"Portfolio digest · week of {today:%d %b %Y}", ""]
    lines.append("Decisions needed")
    if off:
        for p in off:
            reason = (p.get("health_reasons") or ["Off track"])[0]
            lines.append(f"- {p['short']} {p['name']}: {reason}. Decide: re-plan, add help, or pause.")
    else:
        lines.append("- None this week.")
    lines += ["", "Health"]
    lines.append(" · ".join(f"{t['label']} {t['count']}" for t in tiles))
    if risk:
        lines += ["", "At risk"]
        lines += [f"- {p['short']} {p['name']}: {(p.get('health_reasons') or ['At risk'])[0]}" for p in risk]
    changes = [f for f in findings if f["type"] == "change"]
    if changes:
        lines += ["", "Changed this week"] + [f"- {f['text']}" for f in changes]
    data = [f for f in findings if f["type"] in ("data", "sync", "stale")]
    if data:
        lines += ["", "Data to fix"] + [f"- {f['text']}" for f in data]
    stale = [s["name"] for s in sources if s.get("stale")]
    lines += ["", "Evidence: daily sync of JIRA, OpenProject and Multica" +
              (f" ({', '.join(stale)} stale)" if stale else "") + ". Read-only. Drafted by Radar."]
    return "\n".join(lines)
