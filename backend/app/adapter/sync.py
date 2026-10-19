"""The nightly sync (PRD FR-02 to FR-09, FR-17, FR-18).

For each enabled source it reads the tracker through the gateway's source
server, keeps only projects whose name starts with an approved prefix, maps
fields and status, and writes the `app` tables. A source that fails keeps its
last good data and is marked failed, so screens show it as stale. One failing
source never stops the others. Then it computes health for every project and
writes today's snapshot.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapter.readers import SourceCallError, SourceReader
from app.db import session_scope
from app.health import ProjectInfo, MilestoneInfo, Thresholds, assess_all
from app.models.app import (
    Dependency,
    Milestone,
    NonCompliant,
    Prefix,
    Project,
    Risk,
    Snapshot,
    Source,
    Sprint,
    SyncRun,
    TaskSummary,
)
from app.settings import Settings

log = logging.getLogger("adapter.sync")


# -- prefix rule ---------------------------------------------------------------

@dataclass(frozen=True)
class PrefixMatch:
    prefix: str | None
    code: str | None
    name: str
    reason: str | None  # why it did not match


def match_prefix(name_in_tracker: str, prefixes: list[str]) -> PrefixMatch:
    """Longest matching prefix wins (CHL-IT-DAAI- before CHL-IT-). Case does not matter."""
    text = name_in_tracker.strip()
    token = text.split()[0] if text else ""
    upper = token.upper()
    candidates = [p.upper() for p in prefixes if upper.startswith(p.upper()) and len(upper) > len(p)]
    if not candidates:
        reason = "Prefix not recognised" if "-" in token else "No prefix"
        return PrefixMatch(None, None, text, reason)
    prefix = max(candidates, key=len)
    rest = text[len(token):].strip()
    return PrefixMatch(prefix, upper, rest or upper, None)


# -- status mapping ------------------------------------------------------------

class StatusMap:
    def __init__(self, path: Path) -> None:
        raw = json.loads(Path(path).read_text())
        self._default = {k.lower(): v for k, v in raw.get("default", {}).items()}
        self._by_source = {s: {k.lower(): v for k, v in m.items()}
                           for s, m in raw.items() if s not in ("default", "_help") and isinstance(m, dict)}

    def map(self, source_id: str, status: str) -> str | None:
        key = status.strip().lower()
        return self._by_source.get(source_id, {}).get(key) or self._default.get(key)


# -- results -------------------------------------------------------------------

@dataclass
class SourceResult:
    source_id: str
    ok: bool
    projects: int = 0
    non_compliant: int = 0
    errors: list[str] = field(default_factory=list)
    links: list[tuple[str, str, str]] = field(default_factory=list)  # (source_id, from_key, to_key)


@dataclass
class SyncSummary:
    today: date
    sources: list[SourceResult]
    health: dict[str, str]
    duplicates: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "today": self.today.isoformat(),
            "sources": [{"source": s.source_id, "ok": s.ok, "projects": s.projects,
                         "non_compliant": s.non_compliant, "errors": s.errors} for s in self.sources],
            "health": self.health,
            "duplicates": self.duplicates,
        }


def _d(v: str | None) -> date | None:
    return date.fromisoformat(v[:10]) if v else None


def _dt(v: str | None) -> datetime | None:
    if not v:
        return None
    dt = datetime.fromisoformat(v)
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


# -- one source ----------------------------------------------------------------

async def sync_source(reader: SourceReader, source: Source, prefixes: list[str], status_map: StatusMap,
                      now: datetime) -> SourceResult:
    sid = source.id
    res = SourceResult(sid, ok=False)
    async with session_scope() as session:
        run = SyncRun(source_id=sid, started_at=now)
        session.add(run)
        await session.flush()
        run_id = run.id

    try:
        listing = await reader.call(sid, "list_projects")
        matched: list[tuple[dict[str, Any], PrefixMatch]] = []
        rejected: list[tuple[str, str]] = []
        for ref in listing["projects"]:
            m = match_prefix(ref["name"], prefixes)
            if m.code:
                matched.append((ref, m))
            else:
                rejected.append((ref["name"], m.reason or "No prefix"))

        fetched = []
        for ref, m in matched:
            key = ref["key"]
            proj = await reader.call(sid, "get_project", {"key": key})
            status = status_map.map(sid, proj["status"])
            if status is None:
                res.errors.append(f"{m.code}: status '{proj['status']}' has no mapping. Add it to config/status_map.json")
                continue
            fetched.append({
                "match": m, "project": proj, "status": status,
                "milestones": (await reader.call(sid, "get_milestones", {"key": key}))["milestones"],
                "sprints": (await reader.call(sid, "get_sprints", {"key": key}))["sprints"],
                "tasks": await reader.call(sid, "get_task_counts", {"key": key}),
            })
        risks = (await reader.call(sid, "get_risks"))["risks"]
        links = (await reader.call(sid, "get_links"))["links"]
    except SourceCallError as e:
        async with session_scope() as session:
            src = await session.get(Source, sid)
            src.last_sync_at, src.last_status, src.last_error = now, "failed", str(e)
            run = await session.get(SyncRun, run_id)
            run.ended_at, run.result, run.errors_json = datetime.now(UTC), "failed", [str(e)]
        res.errors.append(str(e))
        log.warning("source %s failed, keeping last good data: %s", sid, e)
        return res

    async with session_scope() as session:
        existing = {p.source_key: p for p in (await session.scalars(select(Project).where(Project.source_id == sid))).all()}
        seen: set[str] = set()
        for item in fetched:
            m, proj = item["match"], item["project"]
            key = proj["key"]
            seen.add(key)
            row = existing.get(key) or Project(source_id=sid, source_key=key)
            row.code, row.prefix, row.name = m.code, m.prefix, m.name
            row.team, row.owner = proj.get("team") or source.team, proj.get("owner")
            row.status, row.status_raw = item["status"], proj["status"]
            row.start_date, row.end_date = _d(proj.get("start_date")), _d(proj.get("end_date"))
            row.percent_done, row.strategy_tag = proj.get("percent_done"), proj.get("strategy_tag")
            row.source_url, row.source_updated_at, row.synced_at = proj.get("url"), _dt(proj.get("updated_at")), now
            session.add(row)
            await session.flush()

            await session.execute(delete(Milestone).where(Milestone.project_id == row.id))
            for ms in item["milestones"]:
                session.add(Milestone(project_id=row.id, name=ms["name"], due_date=_d(ms.get("due_date")),
                                      status=ms.get("status", "open"), completed_at=_dt(ms.get("completed_at"))))
            await session.execute(delete(Sprint).where(Sprint.project_id == row.id))
            for sp in item["sprints"]:
                session.add(Sprint(project_id=row.id, name=sp["name"], goal=sp.get("goal"),
                                   start_date=_d(sp.get("start_date")), end_date=_d(sp.get("end_date")),
                                   state=sp.get("state", "active")))
            t = item["tasks"]
            await session.execute(pg_insert(TaskSummary).values(
                project_id=row.id, todo=t["todo"], in_progress=t["in_progress"], done=t["done"], total=t["total"],
            ).on_conflict_do_update(index_elements=["project_id"], set_={
                "todo": t["todo"], "in_progress": t["in_progress"], "done": t["done"], "total": t["total"]}))

        for key in sorted(set(existing) - seen):
            res.errors.append(f"{existing[key].code}: no longer found in {source.name} (kept, last synced "
                              f"{existing[key].synced_at:%Y-%m-%d})" if existing[key].synced_at else
                              f"{existing[key].code}: no longer found in {source.name}")

        by_key = {p.source_key: p for p in (await session.scalars(select(Project).where(Project.source_id == sid))).all()}
        ids = [p.id for p in by_key.values()]
        if ids:
            await session.execute(delete(Risk).where(Risk.project_id.in_(ids), Risk.origin == "tracker"))
        for r in risks:
            p = by_key.get(r.get("project_key") or "")
            if p is None:
                continue
            session.add(Risk(project_id=p.id, title=r["title"], likelihood=r["likelihood"], impact=r["impact"],
                             owner=r.get("owner"), origin="tracker"))

        await session.execute(delete(NonCompliant).where(NonCompliant.source_id == sid))
        for name, reason in rejected:
            session.add(NonCompliant(source_id=sid, name_in_tracker=name, reason=reason, seen_at=now))

        src = await session.get(Source, sid)
        src.last_sync_at, src.last_good_sync_at, src.last_status, src.last_error = now, now, "ok", None
        run = await session.get(SyncRun, run_id)
        run.ended_at, run.projects_read, run.errors_json = datetime.now(UTC), len(fetched), res.errors
        run.result = "ok"

    res.ok, res.projects, res.non_compliant = True, len(fetched), len(rejected)
    res.links = [(sid, link["from_key"], link["to_key"]) for link in links]
    return res


# -- all sources ---------------------------------------------------------------

async def _replace_tracker_links(session: AsyncSession, results: list[SourceResult]) -> None:
    projects = (await session.scalars(select(Project))).all()
    by_source_key = {(p.source_id, p.source_key): p for p in projects}
    by_code: dict[str, Project] = {}
    for p in projects:
        by_code.setdefault(p.code, p)
    synced = [r.source_id for r in results if r.ok]
    synced_ids = [p.id for p in projects if p.source_id in synced]
    if synced_ids:
        await session.execute(delete(Dependency).where(
            Dependency.origin == "tracker", Dependency.from_project_id.in_(synced_ids)))
    for r in results:
        for sid, from_key, to_key in r.links:
            a = by_source_key.get((sid, from_key)) or by_code.get(from_key.upper())
            b = by_source_key.get((sid, to_key)) or by_code.get(to_key.upper())
            if a and b:
                session.add(Dependency(from_project_id=a.id, to_project_id=b.id, kind="blocks", origin="tracker"))


async def recompute_health(session: AsyncSession, settings: Settings, today: date) -> dict[str, str]:
    projects = (await session.scalars(select(Project))).all()
    milestones = (await session.scalars(select(Milestone))).all()
    deps = (await session.scalars(select(Dependency))).all()
    code_of = {p.id: p.code for p in projects}
    ms_by: dict[int, list[MilestoneInfo]] = {}
    for m in milestones:
        ms_by.setdefault(m.project_id, []).append(MilestoneInfo(m.name, m.due_date, m.status == "done"))
    waits: dict[int, list[str]] = {}
    for d in deps:
        waits.setdefault(d.to_project_id, []).append(code_of.get(d.from_project_id, ""))

    infos = [ProjectInfo(p.code, p.status, p.start_date, p.end_date, p.percent_done, p.owner,
                         tuple(ms_by.get(p.id, [])), tuple(waits.get(p.id, []))) for p in projects]
    results = assess_all(infos, today, Thresholds.from_settings(settings))
    out = {}
    for p in projects:
        r = results[p.code]
        p.health, p.health_reasons = r.health, r.reasons
        out[p.code] = r.health
        await session.execute(pg_insert(Snapshot).values(
            date=today, project_id=p.id, status=p.status, health=r.health, percent_done=p.percent_done,
        ).on_conflict_do_update(index_elements=["date", "project_id"], set_={
            "status": p.status, "health": r.health, "percent_done": p.percent_done}))
    return out


async def sync_all(reader: SourceReader, settings: Settings, today: date, only: str | None = None) -> SyncSummary:
    now = datetime.now(UTC)
    status_map = StatusMap(settings.status_map_path)
    async with session_scope() as session:
        sources = (await session.scalars(select(Source).where(Source.enabled.is_(True)).order_by(Source.id))).all()
        prefixes = [p.value for p in (await session.scalars(select(Prefix).where(Prefix.active.is_(True)))).all()]
    if only:
        sources = [s for s in sources if s.id == only]

    results = []
    for source in sources:
        try:
            results.append(await sync_source(reader, source, prefixes, status_map, now))
        except Exception as e:  # noqa: BLE001  one source must never stop the others
            log.exception("source %s crashed", source.id)
            results.append(SourceResult(source.id, ok=False, errors=[f"Unexpected error: {type(e).__name__}"]))

    async with session_scope() as session:
        await _replace_tracker_links(session, results)
        await session.flush()
        health = await recompute_health(session, settings, today)
        codes = (await session.execute(select(Project.code, Project.source_id))).all()
    seen: dict[str, set[str]] = {}
    for code, sid in codes:
        seen.setdefault(code, set()).add(sid)
    duplicates = sorted(f"{code} in {' and '.join(sorted(s))}" for code, s in seen.items() if len(s) > 1)
    return SyncSummary(today, results, health, duplicates)
