"""Radar's nightly check (02:10, after the sync), and acting on approvers' answers.

Runs as the service caller `radar-job`. Everything goes through the gateway:
it reads /portfolio, writes findings, messages and drafts through /radar.
It never sends anything; drafts wait for an approver.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from app.adapter.readers import SourceCallError, SourceReader
from app.radar import writer
from app.radar.rules import check
from app.settings import Settings

log = logging.getLogger("radar.job")
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _fmt(tz: str):
    def f(v: str | None) -> str:
        if not v:
            return "never"
        return datetime.fromisoformat(v).astimezone(ZoneInfo(tz)).strftime("%d %b, %H:%M")
    return f


async def run_check(reader: SourceReader, settings: Settings, today: date, force_digest: bool = False) -> dict[str, Any]:
    status = await reader.call("radar", "get_status")
    if not status.get("radar_on", True):
        log.info("Radar is off in Admin; skipping the check")
        return {"skipped": True}
    rules = status["rules"]
    tz = rules["timezone"]

    projects = (await reader.call("portfolio", "list_projects"))["projects"]
    sources = (await reader.call("portfolio", "get_sync_status"))["sources"]
    findings = [f.as_dict() for f in check(projects, sources, today, stale_days=rules["stale_days"], timezone=tz)]
    saved = await reader.call("radar", "save_findings", {"projects_checked": len(projects), "findings": findings})
    tiles = (await reader.call("portfolio", "get_overview", {"fields": ["tiles"]}))["tiles"]

    # Morning message for everyone: summary, health card, findings card.
    fallback = writer.morning_text(len(projects), findings, sources)
    facts = fallback + "\nFindings:\n" + "\n".join(f"- [{f['severity']}] {f['text']}: {f['detail']}" for f in findings)
    text = await writer.polish(settings, "Write Radar's morning message in 2 to 4 short sentences.", facts, fallback)
    await reader.call("radar", "post_message", {"to": "*", "kind": "divider", "body": f"Today · {today:%d %b}"})
    await reader.call("radar", "post_message", {
        "to": "*", "kind": "radar", "body": text, "mood": "alert" if findings else "happy",
        "payload": {"evidence": writer.evidence_line(sources, _fmt(tz)), "run_id": saved["run_id"]}})
    await reader.call("radar", "post_message", {"to": "*", "kind": "health", "payload": {"tiles": tiles}})
    if findings:
        by_code = {p["code"]: p for p in projects}
        items = [{"severity": f["severity"], "type": f["type"], "text": f["text"], "detail": f["detail"],
                  "project": f["project_code"], "health": by_code.get(f["project_code"] or "", {}).get("health")}
                 for f in findings[:6]]
        await reader.call("radar", "post_message", {"to": "*", "kind": "findings", "payload": {"items": items}})

    # Dependency card when an off-track project blocks another.
    for p in projects:
        if p.get("health") == "off_track" and p.get("blocks"):
            blocked = [q for q in projects if q["short"] in p["blocks"]]
            await reader.call("radar", "post_message", {"to": "*", "kind": "dep", "payload": {
                "from": {"code": p["code"], "short": p["short"], "milestone": p.get("next_milestone"),
                         "due": p.get("next_milestone_due"), "health": p["health"]},
                "to": [{"code": q["code"], "short": q["short"], "milestone": q.get("next_milestone"),
                        "due": q.get("next_milestone_due"), "percent_done": q.get("percent_done"),
                        "health": q["health"]} for q in blocked]}})

    # Ask approvers before drafting a nudge for each off-track project (once a week per project).
    recent = (await reader.call("radar", "list_asks", {"since_hours": 24 * 7}))["asks"]
    asked = {a["payload"].get("project") for a in recent if a["payload"].get("action") == "nudge"}
    asks = 0
    for p in projects:
        if p.get("health") == "off_track" and p["code"] not in asked:
            reason = (p.get("health_reasons") or ["It is off track"])[0]
            await reader.call("radar", "post_message", {
                "to": "role:approver", "kind": "ask", "mood": "asking",
                "body": f"{p['short']} is off track: {reason}. Should I draft a nudge to the {p['short']} owner?",
                "payload": {"action": "nudge", "project": p["code"], "short": f"nudge the {p['short']} owner?"}})
            asks += 1

    # Weekly digest on the digest day, sent at the digest time after approval.
    drafts = 0
    if force_digest or DAYS[today.weekday()] == rules["digest_day"]:
        hh, mm = (int(x) for x in rules["digest_time"].split(":"))
        day = today if DAYS[today.weekday()] == rules["digest_day"] else today + timedelta(
            days=(DAYS.index(rules["digest_day"]) - today.weekday()) % 7)
        send_at = datetime.combine(day, time(hh, mm), ZoneInfo(tz)).isoformat()
        fallback = writer.digest_text(today, tiles, findings, projects, sources)
        body = await writer.polish(settings, "Tidy this Steering Committee digest. Keep the headings and the order "
                                             "(decisions first). Keep it short.", fallback, fallback)
        try:
            await reader.call("radar", "create_draft", {
                "kind": "digest", "title": f"Weekly digest · {today:%d %b}",
                "to": f"{rules['digest_recipients']} · email and Teams", "body": body, "send_at": send_at})
            drafts += 1
        except SourceCallError as e:
            log.info("digest not drafted: %s", e)

    await act_on_answers(reader)
    return {"run_id": saved["run_id"], "findings": len(findings), "new": saved["new"], "asks": asks, "drafts": drafts}


async def act_on_answers(reader: SourceReader) -> int:
    """When an approver says yes to "Should I draft a nudge?", draft it (still needs approval to send)."""
    asks = (await reader.call("radar", "list_asks", {"since_hours": 24 * 7}))["asks"]
    made = 0
    for a in asks:
        pl = a["payload"]
        if pl.get("action") != "nudge" or pl.get("answer") != "yes" or pl.get("draft_id"):
            continue
        p = await reader.call("portfolio", "get_project", {"code": pl["project"]})
        try:
            await reader.call("radar", "create_draft", {
                "kind": "nudge", "title": f"Nudge to {p['short']} owner",
                "to": f"{p.get('owner') or p['short'] + ' owner'} · via Microsoft Teams",
                "body": writer.nudge_text(p, p.get("health_reasons") or []),
                "project": p["code"], "from_ask": a["message_id"]})
            made += 1
        except SourceCallError as e:
            log.info("nudge not drafted for %s: %s", pl["project"], e)
    return made
