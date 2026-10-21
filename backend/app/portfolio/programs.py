"""Program office view: programs with their charter, budget and team, and their
projects with owner and RACI. The data starts from the program office's file
(`python -m app.adapter po-import <file>`). Admins can edit it in Radar (save_* and
delete_* below): edits stay in Radar's own po_* tables, each one is logged in po_activity
with who made it, and nothing is ever written to JIRA, OpenProject or Multica. Radar's own
checks never use this data."""

from __future__ import annotations

import json
import re
import uuid
from datetime import UTC, date, datetime
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
        "kpis": kpis(mine), "updated_at": raw.get("updatedAt"), "updated_by": raw.get("updatedBy"),
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


# -- edits: Admin only, saved in Radar's own tables, never sent to a tracker -------------------

class SaveError(ValueError):
    """The edit was refused. The message is safe to show to the person editing."""


HEALTHS = {"", "Green", "Amber", "Red"}
PRECISIONS = {"", "day", "month"}
LONG_TEXT = 120  # a longer value is logged as "text updated", not copied into the history
MAX_ROWS = 60
PROJECT_TEXT: dict[str, int] = {
    "name": 200, "workstream": 120, "owner": 200, "description": 2000, "impact": 2000, "timingNote": 300,
    "milestoneId": 64, "nextStep": 1000, "decision": 1000, "remarks": 2000,
}
PROGRAM_TEXT: dict[str, int] = {
    "name": 200, "title": 300, "pm": 200, "sponsor": 200, "currency": 12, "statusSummary": 4000, "itscMessage": 2000,
    "problem": 4000, "goal": 4000, "scopeIn": 4000, "scopeOut": 4000, "benefits": 4000, "risks": 4000,
    "assumptions": 4000, "budgetNote": 1000,
}
PROGRAM_LISTS: dict[str, tuple[str, ...]] = {
    "budget": ("item", "prudent", "expansionary", "actual"),
    "milestones": ("id", "name", "start", "target", "actual", "status"),
    "measurables": ("metric", "base", "stretch", "actual", "status"),
    "team": ("id", "name", "role"),
    "steering": ("id", "name", "role"),
}


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _text(raw: dict[str, Any], key: str, limit: int) -> str:
    value = raw.get(key)
    value = "" if value is None else str(value).strip()
    if len(value) > limit:
        raise SaveError(f"{key} is longer than {limit} characters")
    return value


def _iso(raw: dict[str, Any], key: str) -> str:
    value = _text(raw, key, 10)
    if value and (len(value) != 10 or _date(value) is None):
        raise SaveError(f"{key} must be a date written like 2026-10-31")
    return value


def _by(by: str) -> str:
    name = (by or "").strip()[:200]
    if not name:
        raise SaveError("Say who is saving this change")
    return name


def _show(value: Any) -> str:
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)


def _diff(old: dict[str, Any], new: dict[str, Any], fields: list[str]) -> list[dict[str, Any]]:
    changes = []
    for f in fields:
        a, b = old.get(f, ""), new.get(f, "")
        if f == "raci":
            for k in "RACI":
                x, y = (a or {}).get(k, ""), (b or {}).get(k, "")
                if x != y:
                    changes.append({"field": f"raci.{k}", "from": x, "to": y})
        elif isinstance(b, list) or isinstance(a, list):
            if (a or []) != (b or []):
                changes.append({"field": f, "from": f"{len(a or [])} rows", "to": f"{len(b or [])} rows"})
        elif a != b:
            if max(len(_show(a)), len(_show(b))) > LONG_TEXT:
                changes.append({"field": f, "from": "", "to": "(text updated)"})
            else:
                changes.append({"field": f, "from": a, "to": b})
    return changes


def _log(session: AsyncSession, *, by: str, kind: str, ref_id: str, ref_name: str, type_: str,
         changes: list[dict[str, Any]], at: str) -> None:
    session.add(PoActivity(id=uuid.uuid4().hex, at=at, by=by, kind=kind, ref_id=ref_id, ref_name=ref_name,
                           type=type_, changes=changes))


def _clean_project(raw: dict[str, Any], old: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {k: _text(raw, k, n) for k, n in PROJECT_TEXT.items()}
    if not out["name"]:
        raise SaveError("A project needs a name")
    status = _text(raw, "status", 40) or "Planned"
    if status not in STATUSES and status != old.get("status"):
        raise SaveError(f"Status must be one of: {', '.join(STATUSES)}")
    health = _text(raw, "health", 20)
    if health not in HEALTHS and health != old.get("health"):
        raise SaveError("Health must be empty, Green, Amber or Red")
    try:
        pct = int(raw.get("pct") or 0)
    except (TypeError, ValueError):
        raise SaveError("% complete must be a whole number") from None
    if not 0 <= pct <= 100:
        raise SaveError("% complete must be between 0 and 100")
    precision = _text(raw, "targetPrecision", 10)
    if precision not in PRECISIONS:
        raise SaveError("Target precision must be empty, day or month")
    start, target = _iso(raw, "start"), _iso(raw, "target")
    if start and target and target < start:
        raise SaveError("The target date is before the start date")
    given = raw.get("raci")
    r: dict[str, Any] = given if isinstance(given, dict) else {}
    raci = {k: _text(r, k, 500) for k in "RACI"}
    return {**out, "status": status, "health": health, "pct": pct, "targetPrecision": precision,
            "start": start, "target": target, "raci": raci}


PROJECT_FIELDS = [*PROJECT_TEXT, "program", "status", "health", "pct", "targetPrecision", "start", "target", "raci"]


async def _next_project_id(session: AsyncSession) -> str:
    ids = (await session.execute(select(PoProject.id))).scalars().all()
    nums = [int(m.group(1)) for i in ids if (m := re.fullmatch(r"DIG-(\d+)", i))]
    return f"DIG-{(max(nums) if nums else 0) + 1:03d}"


async def save_project(session: AsyncSession, raw: dict[str, Any], by: str) -> dict[str, Any]:
    """Add a project (no id) or change one (with its id). `base_updated_at` guards against a lost edit."""
    by = _by(by)
    pid = _text(raw, "id", 64)
    program_id = _text(raw, "program", 64)
    if not program_id or await session.get(PoProgram, program_id) is None:
        raise SaveError("Pick a program that exists")
    row = await session.get(PoProject, pid) if pid else None
    if pid and row is None:
        raise SaveError(f"There is no project {pid}")
    old: dict[str, Any] = dict(row.data) if row else {}
    base = raw.get("base_updated_at")
    if row is not None and base is not None and base != old.get("updatedAt"):
        raise SaveError("Someone changed this project after you opened it. Reload the page and try again")
    new = {**old, **_clean_project({**old, **raw}, old), "program": program_id}  # a field left out keeps its value
    now = _now()
    if row is None:
        pid = await _next_project_id(session)
        new.update(id=pid, createdAt=now, updatedAt=now, updatedBy=by)
        session.add(PoProject(id=pid, program_id=program_id, name=new["name"], data=new))
        _log(session, by=by, kind="project", ref_id=pid, ref_name=new["name"], type_="created", changes=[], at=now)
        return {"id": pid, "created": True, "changes": 0, "updated_at": now}
    changes = _diff(old, new, PROJECT_FIELDS)
    if not changes:
        return {"id": pid, "created": False, "changes": 0, "updated_at": old.get("updatedAt")}
    new.update(id=pid, updatedAt=now, updatedBy=by)
    row.program_id, row.name, row.data = program_id, new["name"], new
    _log(session, by=by, kind="project", ref_id=pid, ref_name=new["name"], type_="updated", changes=changes, at=now)
    return {"id": pid, "created": False, "changes": len(changes), "updated_at": now}


async def delete_project(session: AsyncSession, project_id: str, by: str) -> dict[str, Any]:
    by = _by(by)
    row = await session.get(PoProject, project_id)
    if row is None:
        raise SaveError(f"There is no project {project_id}")
    name = row.name
    await session.delete(row)
    _log(session, by=by, kind="project", ref_id=project_id, ref_name=name, type_="deleted", changes=[], at=_now())
    return {"id": project_id, "deleted": True}


def _clean_rows(raw: dict[str, Any], key: str, fields: tuple[str, ...]) -> list[dict[str, str]]:
    rows = raw.get(key)
    if rows is None:
        return []
    if not isinstance(rows, list) or len(rows) > MAX_ROWS:
        raise SaveError(f"{key} must be a list of at most {MAX_ROWS} rows")
    out, seen = [], set()
    for r in rows:
        if not isinstance(r, dict):
            raise SaveError(f"Each row of {key} must be an object")
        row = {f: _text(r, f, 300) for f in fields}
        if not any(row[f] for f in fields if f != "id"):
            continue  # an empty row is just removed
        if "id" in fields:
            row["id"] = row["id"] or f"{key[:1]}-{uuid.uuid4().hex[:8]}"
            if row["id"] in seen:
                raise SaveError(f"Two rows of {key} share the id {row['id']}")
            seen.add(row["id"])
        if key == "milestones":
            for d in ("start", "target", "actual"):
                row[d] = _iso(r, d)
        out.append(row)
    return out


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40]


async def save_program(session: AsyncSession, raw: dict[str, Any], by: str) -> dict[str, Any]:
    """Add a program (no id) or change its charter (with its id)."""
    by = _by(by)
    pid = _text(raw, "id", 64)
    row = await session.get(PoProgram, pid) if pid else None
    if pid and row is None:
        raise SaveError(f"There is no program {pid}")
    old: dict[str, Any] = dict(row.data) if row else {}
    base = raw.get("base_updated_at")
    if row is not None and base is not None and base != old.get("updatedAt"):
        raise SaveError("Someone changed this charter after you opened it. Reload the page and try again")
    raw = {**old, **raw}  # a field left out keeps its value
    out: dict[str, Any] = {k: _text(raw, k, n) for k, n in PROGRAM_TEXT.items()}
    if not out["name"]:
        raise SaveError("A program needs a name")
    health = _text(raw, "health", 20)
    if health not in HEALTHS and health != old.get("health"):
        raise SaveError("Health must be empty, Green, Amber or Red")
    start, end = _iso(raw, "start"), _iso(raw, "end")
    if start and end and end < start:
        raise SaveError("The end date is before the start date")
    lists = {k: _clean_rows(raw, k, f) for k, f in PROGRAM_LISTS.items()}
    now = _now()
    if row is None:
        pid = _slug(out["name"])
        if not pid:
            raise SaveError("The program name needs letters or numbers")
        if await session.get(PoProgram, pid) is not None:
            raise SaveError(f"A program with the id {pid} exists already")
        top = (await session.execute(select(PoProgram.sort_order))).scalars().all()
        order = (max(top) if top else 0) + 1
    else:
        try:
            order = int(raw.get("order", old.get("order") or 0))
        except (TypeError, ValueError):
            raise SaveError("Order must be a whole number") from None
    new = {**old, **out, **lists, "health": health, "start": start, "end": end, "order": order, "id": pid}
    if row is None:
        new.update(updatedAt=now, updatedBy=by)
        session.add(PoProgram(id=pid, name=new["name"], sort_order=order, data=new))
        _log(session, by=by, kind="program", ref_id=pid, ref_name=new["name"], type_="created", changes=[], at=now)
        return {"id": pid, "created": True, "changes": 0, "updated_at": now}
    changes = _diff(old, new, [*PROGRAM_TEXT, "health", "start", "end", "order", *PROGRAM_LISTS])
    if not changes:
        return {"id": pid, "created": False, "changes": 0, "updated_at": old.get("updatedAt")}
    new.update(updatedAt=now, updatedBy=by)
    row.name, row.sort_order, row.data = new["name"], order, new
    # A project that pointed at a milestone this charter no longer has loses that link.
    valid = {m["id"] for m in new["milestones"]}
    for p in (await session.execute(select(PoProject).where(PoProject.program_id == pid))).scalars().all():
        if p.data.get("milestoneId") and p.data["milestoneId"] not in valid:
            p.data = {**p.data, "milestoneId": ""}
    _log(session, by=by, kind="program", ref_id=pid, ref_name=new["name"], type_="updated", changes=changes, at=now)
    return {"id": pid, "created": False, "changes": len(changes), "updated_at": now}


async def delete_program(session: AsyncSession, program_id: str, by: str) -> dict[str, Any]:
    by = _by(by)
    row = await session.get(PoProgram, program_id)
    if row is None:
        raise SaveError(f"There is no program {program_id}")
    n = len((await session.execute(select(PoProject.id).where(PoProject.program_id == program_id))).scalars().all())
    if n:
        raise SaveError(f"This program still has {n} project{'s' if n != 1 else ''}. Move or delete them first")
    name = row.name
    await session.delete(row)
    _log(session, by=by, kind="program", ref_id=program_id, ref_name=name, type_="deleted", changes=[], at=_now())
    return {"id": program_id, "deleted": True}
