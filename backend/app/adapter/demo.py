"""Demo data for a fresh database (dev only, mock sources).

1. Sync "yesterday" with every source up, so Multica has last good data from
   18 Oct, as in the designs.
2. Add weekly snapshots for the five weeks before, following the sample's
   portfolio progress curve, so trends and "change since last week" have
   something to show. POS03 went Off track last week; Loyalty App turned At risk this week.
3. Run today's normal sync: Multica fails (expired token) and shows as stale.
4. Turn every MCP tool on (dev only; in production owners do this one by one).
5. Run Radar's first check, and draft this week's digest so approval can be tried.

Everything here is sample data. Never run it against a real database.
"""

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.adapter.readers import GatewayReader
from app.adapter.seed import seed
from app.adapter.sync import sync_all
from app.connectors import SOURCES
from app.connectors.mock import MockConnector, load_sample
from app.db import session_scope
from app.mcp.guard import Gateway
from app.mcp.identity import Caller
from app.mcp.servers import build_registry
from app.models.app import Project, Snapshot, Source
from app.models.mcp import McpToolChange
from app.radar.job import run_check
from app.settings import Settings

ADAPTER = Caller("service", "adapter", frozenset({"adapter"}))
RADAR_JOB = Caller("service", "radar-job", frozenset({"radar"}))


async def _enable_all_tools(registry) -> None:
    """Dev only: turn every tool on, so the demo works end to end. In production
    each owner turns on their own tools."""
    async with session_scope() as session:
        await registry.sync(session)
        for change in (await session.scalars(select(McpToolChange).where(McpToolChange.status == "pending"))).all():
            await registry.decide_change(session, change.id, approve=True, by="demo set-up")
        for name, server in registry.servers.items():
            for tool in server.tools:
                await registry.set_status(session, name, tool, "on", by="demo set-up")


RESET_SQL = ("TRUNCATE app.source, app.prefix, app.agent_run, app.setting, app.radar_message, app.approval, "
             "app.radar_memory RESTART IDENTITY CASCADE")


async def load_demo(settings: Settings, today: date, reset: bool = False) -> dict:
    if settings.app_env == "prod" or settings.source_mode != "mock":
        raise SystemExit("Demo data is only for dev with SOURCE_MODE=mock")
    if reset:
        async with session_scope() as session:
            await session.execute(text(RESET_SQL))
    await seed()
    sample = load_sample(settings.sample_data_path)
    registry = build_registry(settings)
    await _enable_all_tools(registry)

    up = {sid: MockConnector(sid, settings.sample_data_path, force_up=True) for sid in SOURCES}
    yesterday = today - timedelta(days=1)
    await sync_all(GatewayReader(Gateway(registry, settings, {"connectors": up}), ADAPTER), settings, yesterday)

    async with session_scope() as session:
        for s in sample["sources"]:
            last_good = datetime.fromisoformat(s.get("last_good_sync") or s["last_sync"]).astimezone(UTC)
            await session.execute(update(Source).where(Source.id == s["id"]).values(
                last_sync_at=last_good, last_good_sync_at=last_good))

        curve = {date.fromisoformat(w["week"]): w["pct"] for w in sample.get("weekly_avg_progress", [])}
        latest = max(curve.values()) if curve else 0
        last_week = today - timedelta(days=7)
        projects = (await session.scalars(select(Project))).all()
        current = {s.project_id: s for s in (await session.scalars(select(Snapshot).where(Snapshot.date == yesterday))).all()}
        for week, pct in curve.items():
            if week >= yesterday:
                continue
            scale = pct / latest if latest else 1
            for p in projects:
                detail = dict(current[p.id].detail) if p.id in current else {}
                if detail.get("tasks"):
                    detail["tasks"] = {"done": round(detail["tasks"]["done"] * scale),
                                       "total": detail["tasks"]["total"] - (2 if week < last_week else 0)}
                await session.execute(pg_insert(Snapshot).values(
                    date=week, project_id=p.id, status=p.status, health=_past_health(p, week, last_week),
                    percent_done=round((p.percent_done or 0) * scale), detail=detail,
                ).on_conflict_do_nothing())

    gateway = Gateway(registry, settings, {"connectors": {
        sid: MockConnector(sid, settings.sample_data_path) for sid in SOURCES}})
    real = await sync_all(GatewayReader(gateway, ADAPTER), settings, today)
    # Radar's first check, with this week's digest drafted so the approval flow can be tried.
    radar = await run_check(GatewayReader(gateway, RADAR_JOB), settings, today, force_digest=True)
    return {**real.as_dict(), "radar": radar}


def _past_health(p: Project, week: date, last_week: date) -> str | None:
    """POS03 went Off track last week; Loyalty App, which waits for it, became At risk this week."""
    if p.code == "CHL-DP-POS03":
        return "off_track" if week >= last_week else "on_track"
    if p.code == "CHL-DP-LOYAL02":
        return "on_track"
    return p.health
