"""Program office view: programs with their charter, budget and team, and their
projects with owner and RACI. The data is imported from the program office's file
(`python -m app.adapter po-import <file>`) and is read-only here: nothing in the
app edits it. Radar's own checks never use it."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.app import PoActivity, PoProgram, PoProject

CLOSED = {"Completed", "Cancelled"}
ACTIVE = {"In Progress", "In UAT", "Dev Complete"}
STATUSES = ["Completed", "Dev Complete", "In UAT", "In Progress", "Pending Approval", "Planned", "On Hold", "Cancelled"]

# What a finished charter has. Label, then how to tell it is filled in.
CHARTER_CHECKS: list[tuple[str, str]] = [
    ("Program manager", "pm"), ("Sponsor", "sponsor"), ("Start and end dates", "dates"),
    ("Problem statement", "problem"), ("Goal", "goal"), ("Scope", "scopeIn"), ("Benefits", "benefits"),
    ("Risks", "risks"), ("Assumptions", "assumptions"), ("Budget", "budget"), ("Milestones", "milestones"),
    ("Measurables", "measurables"), ("Project team", "team"), ("Steering committee", "steering"),
]


def _names(value: Any) -> list[str]:
    return [n.strip() for n in str(value or "").split(",") if n.strip()]


def _num(v: Any) -> float | None:
    try:
        return None if v in (None, "") else float(v)
    except (TypeError, ValueError):
        return None


def _date(v: Any) -> date | None:
    try:
        return date.fromisoformat(str(v)[:10]) if v else None
    except ValueError:
        return None


def is_open(status: str) -> bool:
    return status not in CLOSED


def charter_checks(pr: dict[str, Any]) -> list[dict[str, Any]]:
    def filled(key: str) -> bool:
        if key == "dates":
            return bool(pr.get("start") and pr.get("end"))
        return bool(pr.get(key))
    return [{"label": label, "done": filled(key)} for label, key in CHARTER_CHECKS]


def budget_totals(pr: dict[str, Any]) -> dict[str, Any]:
    rows = pr.get("budget") or []
    def total(k: str) -> float | None:
        vals = [_num(r.get(k)) for r in rows]
        vals = [v for v in vals if v is not None]
        return sum(vals) if vals else None
    return {"prudent": total("prudent"), "expansionary": total("expansionary"), "actual": total("actual")}


def project_row(raw: dict[str, Any], today: date) -> dict[str, Any]:
    status = raw.get("status") or "Planned"
    target = _date(raw.get("target"))
    days = (target - today).days if target else None
    raci = {k: (raw.get("raci") or {}).get(k, "") for k in "RACI"}
    return {
        "id": raw.get("id", ""), "name": raw.get("name", ""), "program": raw.get("program", ""),
        "workstream": raw.get("workstream", ""), "status": status, "health": raw.get("health", ""),
        "pct": int(raw.get("pct") or 0), "target_precision": raw.get("targetPrecision", ""), "owner": raw.get("owner", ""), "start": raw.get("start", ""),
        "target": raw.get("target", ""), "timing_note": raw.get("timingNote", ""),
        "impact": raw.get("impact", ""), "description": raw.get("description", ""),
        "next_step": raw.get("nextStep", ""), "decision": raw.get("decision", ""), "remarks": raw.get("remarks", ""),
        "milestone_id": raw.get("milestoneId", ""), "raci": raci,
        "days_to_target": days, "open": is_open(status),
        "updated_at": raw.get("updatedAt"), "updated_by": raw.get("updatedBy"),
    }


def kpis(projects: list[dict[str, Any]]) -> dict[str, int]:
    open_ = [p for p in projects if p["open"]]
    due = [p for p in open_ if p["days_to_target"] is not None]
    return {
        "projects": len(projects),
        "completed": sum(p["status"] == "Completed" for p in projects),
        "active": sum(p["status"] in ACTIVE for p in projects),
        "pending_approval": sum(p["status"] == "Pending Approval" for p in projects),
        "planned": sum(p["status"] == "Planned" for p in projects),
        "due_30": sum(0 <= p["days_to_target"] <= 30 for p in due),
        "past_target": sum(p["days_to_target"] < 0 for p in due),
        "no_accountable": sum(len(_names(p["raci"]["A"])) != 1 for p in open_),
    }


def program_row(raw: dict[str, Any], projects: list[dict[str, Any]]) -> dict[str, Any]:
    checks = charter_checks(raw)
    mine = [p for p in projects if p["program"] == raw.get("id")]
    ms_ids = {m.get("id"): m.get("name", "") for m in raw.get("milestones") or []}
    for p in mine:
        p["milestone"] = ms_ids.get(p["milestone_id"], "")
    return {
        **{k: raw.get(k, "") for k in ("id", "name", "title", "pm", "sponsor", "start", "end", "health", "currency",
                                       "statusSummary", "itscMessage", "problem", "goal", "scopeIn", "scopeOut",
                                       "benefits", "risks", "assumptions", "budgetNote")},
        "budget": raw.get("budget") or [], "budget_totals": budget_totals(raw),
        "milestones": raw.get("milestones") or [], "measurables": raw.get("measurables") or [],
        "team": raw.get("team") or [], "steering": raw.get("steering") or [],
        "checks": checks, "completeness": round(100 * sum(c["done"] for c in checks) / len(checks)),
        "kpis": kpis(mine),
    }


async def programs_view(session: AsyncSession, today: date) -> dict[str, Any]:
    progs = (await session.execute(select(PoProgram).order_by(PoProgram.sort_order, PoProgram.name))).scalars().all()
    rows = (await session.execute(select(PoProject))).scalars().all()
    projects = [project_row({**r.data, "id": r.id, "program": r.program_id}, today) for r in rows]
    projects.sort(key=lambda p: (p["program"], p["workstream"], p["id"]))
    imported = max((r.imported_at for r in [*progs, *rows]), default=None)
    acts = (await session.execute(select(PoActivity).order_by(PoActivity.at.desc()).limit(200))).scalars().all()
    activity = [{"id": a.id, "at": a.at, "by": a.by, "kind": a.kind, "ref_id": a.ref_id, "ref_name": a.ref_name,
                 "type": a.type, "changes": a.changes or []} for a in acts]
    return {
        "today": today.isoformat(), "activity": activity,
        "programs": [program_row({**p.data, "id": p.id}, projects) for p in progs],
        "projects": projects, "kpis": kpis(projects), "statuses": STATUSES,
        "imported_at": imported.isoformat() if imported else None,
    }


async def import_file(session: AsyncSession, path: Path) -> dict[str, int]:
    """Replace the program office data with the contents of a program-office JSON file."""
    doc = json.loads(path.read_text(encoding="utf-8"))
    programs = doc.get("programs") or {}
    projects = doc.get("projects") or {}
    await session.execute(delete(PoActivity))
    await session.execute(delete(PoProject))
    await session.execute(delete(PoProgram))
    for key, value in programs.items():
        data = value.get("data", value)
        session.add(PoProgram(id=str(data.get("id") or key), name=data.get("name", ""),
                              sort_order=int(data.get("order") or 0), data=data))
    for key, value in projects.items():
        data = value.get("data", value)
        session.add(PoProject(id=str(data.get("id") or key), program_id=str(data.get("program", "")),
                              name=data.get("name", ""), data=data))
    activity = doc.get("activity") or {}
    for key, value in activity.items():
        data = value.get("data", value)
        session.add(PoActivity(id=str(key), at=str(data.get("at") or ""), by=str(data.get("by") or ""),
                               kind=str(data.get("kind") or "project"), ref_id=str(data.get("projectId") or ""),
                               ref_name=str(data.get("projectName") or ""), type=str(data.get("type") or "updated"),
                               changes=data.get("changes") if isinstance(data.get("changes"), list) else []))
    return {"programs": len(programs), "projects": len(projects), "activity": len(activity)}
