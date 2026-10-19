"""Read models for the screens and agents. Everything the Overview, Project,
Roadmap and Risks screens show comes from here, through `/portfolio/mcp`.
Every answer carries its evidence: source, sync time and whether data is stale.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.health import AT_RISK, DONE, LABELS, OFF_TRACK, ON_TRACK
from app.models.app import (
    AgentRun,
    Dependency,
    Finding,
    Milestone,
    Project,
    Risk,
    Snapshot,
    Source,
    Sprint,
    TaskSummary,
)

HEALTH_ORDER = [ON_TRACK, AT_RISK, OFF_TRACK, DONE]
LIKELIHOOD = ["Low", "Medium", "High"]


def short_code(p: Project) -> str:
    return p.code[len(p.prefix):] if p.prefix and p.code.startswith(p.prefix) else p.code


def _n(count: int, word: str) -> str:
    return f"{count} {word}{'' if count == 1 else 's'}"


def _iso(v: date | datetime | None) -> str | None:
    return v.isoformat() if v else None


class PortfolioData:
    """All data one request needs, loaded once."""

    def __init__(self) -> None:
        self.projects: list[Project] = []
        self.sources: dict[str, Source] = {}
        self.milestones: dict[int, list[Milestone]] = defaultdict(list)
        self.sprints: dict[int, list[Sprint]] = defaultdict(list)
        self.tasks: dict[int, TaskSummary] = {}
        self.deps: list[Dependency] = []
        self.risks: list[Risk] = []
        self.by_id: dict[int, Project] = {}

    @classmethod
    async def load(cls, session: AsyncSession) -> PortfolioData:
        s = cls()
        s.projects = list((await session.scalars(select(Project).order_by(Project.code, Project.source_id))).all())
        s.by_id = {p.id: p for p in s.projects}
        s.sources = {x.id: x for x in (await session.scalars(select(Source))).all()}
        for m in (await session.scalars(select(Milestone).order_by(Milestone.due_date.nulls_last(), Milestone.id))).all():
            s.milestones[m.project_id].append(m)
        for sp in (await session.scalars(select(Sprint).order_by(Sprint.start_date))).all():
            s.sprints[sp.project_id].append(sp)
        s.tasks = {t.project_id: t for t in (await session.scalars(select(TaskSummary))).all()}
        s.deps = list((await session.scalars(select(Dependency))).all())
        s.risks = list((await session.scalars(select(Risk).order_by(Risk.id))).all())
        return s

    def stale(self, p: Project) -> bool:
        src = self.sources.get(p.source_id)
        return bool(src and src.last_status == "failed")

    def next_milestone(self, p: Project) -> Milestone | None:
        open_ms = [m for m in self.milestones[p.id] if m.status != "done"]
        return open_ms[0] if open_ms else None

    def waits_for(self, p: Project) -> list[Project]:
        return [self.by_id[d.from_project_id] for d in self.deps if d.to_project_id == p.id and d.from_project_id in self.by_id]

    def blocks(self, p: Project) -> list[Project]:
        return [self.by_id[d.to_project_id] for d in self.deps if d.from_project_id == p.id and d.to_project_id in self.by_id]


def _source_info(src: Source | None) -> dict[str, Any]:
    if src is None:
        return {}
    return {"id": src.id, "name": src.name, "team": src.team, "status": src.last_status,
            "last_sync_at": _iso(src.last_sync_at), "last_good_sync_at": _iso(src.last_good_sync_at),
            "error": src.last_error, "stale": src.last_status == "failed"}


def project_row(s: PortfolioData, p: Project) -> dict[str, Any]:
    nm = s.next_milestone(p)
    return {
        "code": p.code, "short": short_code(p), "name": p.name, "health": p.health,
        "health_label": LABELS.get(p.health or "", "Unknown"), "health_reasons": p.health_reasons or [],
        "team": p.team, "owner": p.owner, "source": p.source_id,
        "source_name": s.sources[p.source_id].name if p.source_id in s.sources else p.source_id,
        "stale": s.stale(p), "status": p.status, "percent_done": p.percent_done,
        "next_milestone": nm.name if nm else None, "next_milestone_due": _iso(nm.due_date) if nm else None,
        "strategy": p.strategy_tag, "prefix": p.prefix, "updated": _iso(p.source_updated_at),
        "synced_at": _iso(p.synced_at), "source_url": p.source_url,
        "start_date": _iso(p.start_date), "end_date": _iso(p.end_date),
    }


def matches(row: dict[str, Any], f: dict[str, Any]) -> bool:
    for key in ("health", "source", "prefix", "team", "status"):
        want = f.get(key)
        if want and row.get(key) != want:
            return False
    q = (f.get("q") or "").strip().lower()
    return not q or q in row["code"].lower() or q in row["name"].lower()


async def _snapshots(session: AsyncSession, since: date) -> dict[date, dict[int, Snapshot]]:
    out: dict[date, dict[int, Snapshot]] = defaultdict(dict)
    for snap in (await session.scalars(select(Snapshot).where(Snapshot.date >= since))).all():
        out[snap.date][snap.project_id] = snap
    return out


def _on_or_before(days: dict[date, Any], target: date) -> date | None:
    earlier = [d for d in days if d <= target]
    return max(earlier) if earlier else None


async def list_projects(session: AsyncSession, filters: dict[str, Any]) -> dict[str, Any]:
    s = await PortfolioData.load(session)
    rows = [project_row(s, p) for p in s.projects]
    shown = [r for r in rows if matches(r, filters)]
    return {"total": len(rows), "count": len(shown), "projects": shown}


async def latest_radar(session: AsyncSession) -> dict[str, Any]:
    run = await session.scalar(select(AgentRun).where(AgentRun.ended_at.is_not(None)).order_by(AgentRun.id.desc()))
    if run is None:
        return {"checked_at": None, "projects_checked": 0, "count": 0, "items": []}
    findings = (await session.scalars(select(Finding).where(
        Finding.run_id == run.id, Finding.dismissed_at.is_(None)).order_by(Finding.id))).all()
    rank = {"high": 0, "medium": 1, "low": 2}
    findings = sorted(findings, key=lambda f: rank.get(f.severity, 3))
    return {"checked_at": _iso(run.ended_at), "projects_checked": run.projects_checked, "count": len(findings),
            "items": [{"id": f.id, "type": f.type, "severity": f.severity, "text": f.text,
                       "project_id": f.project_id, "evidence": f.evidence_json} for f in findings]}


async def overview(session: AsyncSession, today: date) -> dict[str, Any]:
    s = await PortfolioData.load(session)
    rows = [project_row(s, p) for p in s.projects]
    snaps = await _snapshots(session, today - timedelta(days=42))
    last_week_day = _on_or_before(snaps, today - timedelta(days=7))
    last_week = snaps.get(last_week_day, {}) if last_week_day else {}

    tiles = []
    for h in HEALTH_ORDER:
        now_codes = [p for p in s.projects if p.health == h]
        before = [pid for pid, snap in last_week.items() if snap.health == h]
        change = len(now_codes) - len(before) if last_week else None
        new = [short_code(p) for p in now_codes if last_week and last_week.get(p.id) and last_week[p.id].health != h]
        note = None
        if h == OFF_TRACK and now_codes:
            parts = []
            for p in now_codes:
                since = today
                for d in sorted(snaps, reverse=True):
                    if snaps[d].get(p.id) and snaps[d][p.id].health == OFF_TRACK:
                        since = d
                    else:
                        break
                parts.append(f"{short_code(p)} · off track since {since:%d %b}")
            note = "; ".join(parts)
        elif h == DONE and now_codes:
            note = ", ".join(f"{p.name}" + (f", ends {p.end_date:%d %b}" if p.end_date else "") for p in now_codes)
        elif change is None:
            note = "No history yet"
        elif change == 0:
            note = "No change from last week"
        else:
            note = f"{change:+d} since last week" + (f" ({', '.join(new)})" if new and change > 0 else "")
        tiles.append({"health": h, "label": LABELS[h], "count": len(now_codes), "change": change, "note": note})

    sources = []
    for src in sorted(s.sources.values(), key=lambda x: ["jira", "openproject", "multica"].index(x.id)
                      if x.id in ("jira", "openproject", "multica") else 9):
        ps = [p for p in s.projects if p.source_id == src.id]
        pcts = [p.percent_done for p in ps if p.percent_done is not None]
        sources.append({**_source_info(src), "projects": len(ps),
                        "avg_percent_done": round(sum(pcts) / len(pcts)) if pcts else None})

    trend = []
    for w in range(5, -1, -1):
        d = _on_or_before(snaps, today - timedelta(days=7 * w))
        if d is None:
            continue
        vals = [x.percent_done for x in snaps[d].values() if x.percent_done is not None]
        if vals and (not trend or trend[-1]["date"] != d.isoformat()):
            trend.append({"date": d.isoformat(), "avg_percent_done": round(sum(vals) / len(vals))})

    upcoming = []
    for p in s.projects:
        nm = s.next_milestone(p)
        if nm and nm.due_date:
            days = (nm.due_date - today).days
            waits = [short_code(w) for w in s.waits_for(p) if w.health == OFF_TRACK]
            note = (f"{-days} days overdue" if days < 0 else f"in {days} days") + \
                   (f" · waits for {', '.join(waits)}" if waits else "")
            upcoming.append({"date": nm.due_date.isoformat(), "name": nm.name, "code": p.code, "short": short_code(p),
                             "project": p.name, "overdue": days < 0, "days": days, "note": note, "health": p.health})
    upcoming.sort(key=lambda m: m["date"])

    last_sync = max((src.last_sync_at for src in s.sources.values() if src.last_sync_at), default=None)
    return {
        "today": today.isoformat(), "last_sync_at": _iso(last_sync), "total": len(rows),
        "tiles": tiles, "sources": sources, "trend": trend,
        "progress": [{"code": r["code"], "short": r["short"], "source": r["source"],
                      "percent_done": r["percent_done"], "health": r["health"]} for r in rows],
        "next_milestones": upcoming[:6],
        "projects": rows,
        "radar": await latest_radar(session),
    }


def _changes(today_snap: Snapshot | None, week_snap: Snapshot | None, sprints: list[Sprint], today: date) -> list[str]:
    if today_snap is None or week_snap is None:
        return ["No history from last week yet"]
    out = []
    if today_snap.percent_done != week_snap.percent_done:
        out.append(f"Progress {week_snap.percent_done}% to {today_snap.percent_done}%")
    else:
        out.append(f"Progress unchanged at {today_snap.percent_done}%")
    if today_snap.health != week_snap.health:
        out.append(f"Health {LABELS.get(week_snap.health or '', '?')} to {LABELS.get(today_snap.health or '', '?')}")
    if today_snap.status != week_snap.status:
        out.append(f"Status {week_snap.status} to {today_snap.status}")
    for sp in sprints:
        if sp.start_date and today - timedelta(days=7) < sp.start_date <= today:
            out.append(f"{sp.name} started on {sp.start_date:%d %b}")
    t_now, t_then = (today_snap.detail or {}).get("tasks"), (week_snap.detail or {}).get("tasks")
    if t_now and t_then:
        closed = t_now["done"] - t_then["done"]
        added = t_now["total"] - t_then["total"]
        out.append(f"{_n(max(closed, 0), 'task')} closed, {_n(max(added, 0), 'new task')} added")
    m_now, m_then = (today_snap.detail or {}).get("milestones"), (week_snap.detail or {}).get("milestones")
    if m_now is not None and m_then is not None:
        moved = [f"'{n}' moved from {m_then[n]} to {d}" for n, d in m_now.items() if n in m_then and m_then[n] != d]
        out += [f"Milestone {m}" for m in moved] or ["No milestone dates changed"]
    return out


async def project_detail(session: AsyncSession, code: str, today: date) -> dict[str, Any] | None:
    s = await PortfolioData.load(session)
    matches_ = [p for p in s.projects if p.code == code.upper()]
    if not matches_:
        return None
    p = matches_[0]
    row = project_row(s, p)
    ms = s.milestones[p.id]
    nm = s.next_milestone(p)
    sprint = next((sp for sp in reversed(s.sprints[p.id]) if sp.state == "active"), None)
    t = s.tasks.get(p.id)
    snaps = await _snapshots(session, today - timedelta(days=42))
    trend = []
    for w in range(5, -1, -1):
        d = _on_or_before(snaps, today - timedelta(days=7 * w))
        if d and p.id in snaps[d] and (not trend or trend[-1]["date"] != d.isoformat()):
            trend.append({"date": d.isoformat(), "percent_done": snaps[d][p.id].percent_done})
    today_d = _on_or_before(snaps, today)
    week_d = _on_or_before(snaps, today - timedelta(days=7))
    changes = _changes(snaps[today_d].get(p.id) if today_d else None,
                       snaps[week_d].get(p.id) if week_d else None, s.sprints[p.id], today)
    risks = [r for r in s.risks if r.project_id == p.id]
    finding = await session.scalar(select(Finding).where(Finding.project_id == p.id, Finding.dismissed_at.is_(None))
                                   .order_by(Finding.id.desc()))
    return {
        **row,
        "source_info": _source_info(s.sources.get(p.source_id)),
        "source_key": p.source_key, "status_raw": p.status_raw,
        "also_in": [x.source_id for x in matches_[1:]],
        "tasks": {"todo": t.todo, "in_progress": t.in_progress, "done": t.done, "total": t.total} if t else None,
        "milestones": [{"name": m.name, "due_date": _iso(m.due_date), "status": m.status,
                        "completed_at": _iso(m.completed_at), "next": nm is not None and m.id == nm.id,
                        "overdue": m.status != "done" and m.due_date is not None and m.due_date < today}
                       for m in ms],
        "milestones_done": sum(1 for m in ms if m.status == "done"),
        "days_left": (p.end_date - today).days if p.end_date else None,
        "sprint": {"name": sprint.name, "goal": sprint.goal, "start_date": _iso(sprint.start_date),
                   "end_date": _iso(sprint.end_date)} if sprint else None,
        "trend": trend,
        "changes": changes,
        "risks": [risk_row(s, r) for r in risks],
        "waits_for": [{"code": w.code, "short": short_code(w), "name": w.name, "health": w.health} for w in s.waits_for(p)],
        "blocks": [{"code": b.code, "short": short_code(b), "name": b.name, "health": b.health} for b in s.blocks(p)],
        "radar_note": finding.text if finding else None,
    }


async def history(session: AsyncSession, code: str, weeks: int, today: date) -> dict[str, Any] | None:
    p = await session.scalar(select(Project).where(Project.code == code.upper()))
    if p is None:
        return None
    rows = (await session.scalars(select(Snapshot).where(
        Snapshot.project_id == p.id, Snapshot.date >= today - timedelta(days=7 * weeks)).order_by(Snapshot.date))).all()
    return {"code": p.code, "snapshots": [{"date": _iso(r.date), "status": r.status, "health": r.health,
                                           "percent_done": r.percent_done} for r in rows]}


def risk_row(s: PortfolioData, r: Risk) -> dict[str, Any]:
    p = s.by_id.get(r.project_id) if r.project_id else None
    return {"id": f"R{r.id}", "title": r.title, "likelihood": r.likelihood, "impact": r.impact, "owner": r.owner,
            "origin": r.origin, "review_date": _iso(r.review_date),
            "project": {"code": p.code, "short": short_code(p), "name": p.name, "health": p.health} if p else None}


async def risks(session: AsyncSession, code: str | None) -> dict[str, Any]:
    s = await PortfolioData.load(session)
    rows = [risk_row(s, r) for r in s.risks if not code or (r.project_id and s.by_id[r.project_id].code == code.upper())]
    matrix = {li: {im: 0 for im in LIKELIHOOD} for li in LIKELIHOOD}
    for r in rows:
        if r["likelihood"] in matrix and r["impact"] in matrix[r["likelihood"]]:
            matrix[r["likelihood"]][r["impact"]] += 1
    strategy: dict[str, dict[str, Any]] = {}
    for p in s.projects:
        tag = p.strategy_tag or "Not tagged"
        e = strategy.setdefault(tag, {"tag": tag, "projects": 0, **{h: 0 for h in HEALTH_ORDER}})
        e["projects"] += 1
        if p.health in HEALTH_ORDER:
            e[p.health] += 1
    return {"count": len(rows), "risks": rows, "matrix": matrix,
            "strategy": sorted(strategy.values(), key=lambda e: -e["projects"])}


async def dependencies(session: AsyncSession, code: str | None) -> dict[str, Any]:
    s = await PortfolioData.load(session)
    out = []
    for d in s.deps:
        a, b = s.by_id.get(d.from_project_id), s.by_id.get(d.to_project_id)
        if not a or not b or (code and code.upper() not in (a.code, b.code)):
            continue
        out.append({"from": {"code": a.code, "short": short_code(a), "name": a.name, "health": a.health},
                    "to": {"code": b.code, "short": short_code(b), "name": b.name, "health": b.health},
                    "kind": d.kind, "origin": d.origin,
                    "at_risk": a.health == OFF_TRACK})
    return {"count": len(out), "dependencies": out}


async def roadmap(session: AsyncSession, today: date) -> dict[str, Any]:
    s = await PortfolioData.load(session)
    starts = [p.start_date for p in s.projects if p.start_date]
    ends = [p.end_date for p in s.projects if p.end_date]
    deps = await dependencies(session, None)
    return {
        "today": today.isoformat(),
        "window": {"start": _iso(min(starts)) if starts else None, "end": _iso(max(ends)) if ends else None},
        "projects": [{**project_row(s, p), "milestones": [
            {"name": m.name, "due_date": _iso(m.due_date), "status": m.status,
             "overdue": m.status != "done" and m.due_date is not None and m.due_date < today}
            for m in s.milestones[p.id]]} for p in sorted(s.projects, key=lambda x: (x.start_date or date.max, x.code))],
        "dependencies": deps["dependencies"],
    }


async def sync_status(session: AsyncSession) -> dict[str, Any]:
    s = await PortfolioData.load(session)
    order = ["jira", "openproject", "multica"]
    srcs = sorted(s.sources.values(), key=lambda x: order.index(x.id) if x.id in order else 9)
    return {"sources": [{**_source_info(src), "projects": sum(1 for p in s.projects if p.source_id == src.id)}
                        for src in srcs]}
