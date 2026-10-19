"""Load test: 500 projects (PRD: "overview loads in under 3 seconds for 500 projects").

    createdb radar_load   # once
    DATABASE_URL=postgresql+psycopg://radar:radar@localhost:5432/radar_load \
        python -m loadtest.run --projects 500 --days 365

It builds a sample file with N projects across the three sources (real prefixes,
milestones, links, risks), loads it with the demo loader, adds a year of daily
snapshots, then times every portfolio tool through the gateway (guard, audit and
all) and writes loadtest/results.json. Never point it at a real database: the
demo loader empties the portfolio tables.

The web pages are timed separately with web/scripts/loadtest-pages.mjs against a gateway
running on this database.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import statistics
import time
from datetime import date, timedelta
from pathlib import Path

from sqlalchemy import select, text

from app.adapter.demo import load_demo
from app.adapter.readers import GatewayReader
from app.radar.job import run_check
from app.db import get_engine, session_scope
from app.mcp.guard import Gateway
from app.mcp.identity import Caller
from app.mcp.servers import build_registry
from app.models.app import Project
from app.settings import BACKEND_DIR, get_settings

HERE = Path(__file__).parent
SAMPLE = BACKEND_DIR.parent / "design" / "sample-data.json"
VIEWER = Caller("human", "load@cityholdings.dev", frozenset({"viewer"}))
RADAR_JOB = Caller("service", "radar-job", frozenset({"radar"}))
SOURCES = [("jira", "Digital Teams", ["CHL-DP-", "CHL-IT-", "CMHL-IT-"]),
           ("openproject", "Data Team", ["CHL-IT-DAAI-"]),
           ("multica", "AI and Agent Teams", ["CHL-IT-DAAI-", "CHL-IT-"])]
STATUSES = ["In progress"] * 6 + ["Not started", "Done", "On hold"]
WORDS = ("Customer Loyalty Data Mobile Payments Store Supply Analytics Portal Wallet Pricing Forecast HR "
         "Vendor Inventory Delivery Chat Agent Insights Lake Billing Audit Kiosk Scanner Ledger").split()


def build_sample(n: int, seed: int = 7) -> dict:
    rnd = random.Random(seed)
    base = json.loads(SAMPLE.read_text())
    as_of = date.fromisoformat(base["as_of"][:10])
    aspirations = ["Innovative Market Leader", "Benchmark of Excellence", "Employer of Choice",
                   "Preferred Business Partner", "Homegrown Champion", None]
    projects = []
    for i in range(n):
        sid, team, prefixes = SOURCES[i % 3]
        start = as_of - timedelta(days=rnd.randint(10, 300))
        end = start + timedelta(days=rnd.randint(60, 420))
        status = rnd.choice(STATUSES)
        pct = 100 if status == "Done" else 0 if status == "Not started" else rnd.randint(5, 95)
        projects.append({
            "code": f"{rnd.choice(prefixes)}{''.join(rnd.choice('ABCDEFGHJKLMNPQRSTUVWXYZ') for _ in range(3))}{i:03d}",
            "name": f"{rnd.choice(WORDS)} {rnd.choice(WORDS)} {i}", "team": team, "source": sid, "status": status,
            "percent_done": pct, "next_milestone": f"Milestone {rnd.randint(1, 9)}",
            "next_milestone_due": (as_of + timedelta(days=rnd.randint(-20, 60))).isoformat(),
            "strategy_tag": rnd.choice(aspirations), "start_date": start.isoformat(), "end_date": end.isoformat(),
            "source_updated_at": (as_of - timedelta(days=rnd.choice([0, 1, 2, 5, 20]))).isoformat(),
            "owner": f"Owner {i % 60} (sample)",
        })
    codes = [p["code"] for p in projects]
    deps = [{"from": a, "to": b, "kind": "blocks"} for a, b in
            {(rnd.choice(codes), rnd.choice(codes)) for _ in range(n // 4)} if a != b]
    risks = [{"id": f"R{k}", "title": f"Risk {k}", "project": rnd.choice(codes),
              "likelihood": rnd.choice(["Low", "Medium", "High"]), "impact": rnd.choice(["Low", "Medium", "High"])}
             for k in range(n // 5)]
    non_compliant = [{"name": f"Unprefixed project {k}", "source": SOURCES[k % 3][0], "reason": "No prefix"}
                     for k in range(n // 25)]
    return {**base, "note": f"Load test sample: {n} generated projects. Not real.", "projects": projects,
            "dependencies": deps, "risks": risks, "non_compliant": non_compliant}


async def add_daily_history(days: int, today: date) -> int:
    """A snapshot per project per day, like a year of nightly syncs."""
    async with session_scope() as session:
        ids = [p.id for p in (await session.scalars(select(Project))).all()]
        await session.execute(text("DELETE FROM app.snapshot WHERE date < :d"), {"d": today - timedelta(days=35)})
    rnd = random.Random(3)
    rows = []
    for pid in ids:
        pct = rnd.randint(0, 20)
        for d in range(days, 35, -1):
            pct = min(100, pct + rnd.choice([0, 0, 1, 2]))
            rows.append({"d": today - timedelta(days=d), "p": pid, "h": rnd.choice(["green"] * 6 + ["amber", "red"]),
                         "pct": pct})
    async with get_engine().begin() as conn:
        for i in range(0, len(rows), 5000):
            await conn.execute(text("INSERT INTO app.snapshot (date, project_id, status, health, percent_done, detail) "
                                    "VALUES (:d, :p, 'In progress', :h, :pct, '{}')"), rows[i:i + 5000])
        await conn.execute(text("ANALYZE app.snapshot"))
    return len(rows)


async def time_tools(gw: Gateway, runs: int) -> dict:
    async with session_scope() as session:
        some = (await session.scalars(select(Project.code).limit(1))).first()
    calls = [("get_overview", {}), ("list_projects", {}), ("list_projects", {"health": "off_track"}),
             ("get_project", {"code": some}), ("get_history", {"code": some, "weeks": 26}), ("get_roadmap", {}),
             ("get_dependencies", {}), ("get_risks", {}), ("get_sync_status", {})]
    out = {}
    for tool, args in calls:
        times, size = [], 0
        for _ in range(runs):
            t = time.perf_counter()
            r = await gw.call(VIEWER, "portfolio", tool, args)
            times.append((time.perf_counter() - t) * 1000)
            assert r.outcome == "ok", (tool, r.message)
            size = len(json.dumps(r.value, default=str))
        label = tool + ("(" + ",".join(f"{k}={v}" for k, v in args.items() if k != "code") + ")" if args and "code" not in args else "")
        out[label] = {"p50_ms": round(statistics.median(times), 1), "max_ms": round(max(times), 1), "kb": round(size / 1024, 1)}
    return out


async def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--projects", type=int, default=500)
    p.add_argument("--days", type=int, default=365)
    p.add_argument("--runs", type=int, default=10)
    a = p.parse_args()
    settings = get_settings()
    if "radar_load" not in settings.database_url:
        raise SystemExit("Refusing: DATABASE_URL must point at the radar_load database")
    sample_path = HERE / "sample-500.json"
    sample_path.write_text(json.dumps(build_sample(a.projects)))
    settings = settings.model_copy(update={"sample_data_path": sample_path, "app_env": "dev"})
    today = date.fromisoformat(json.loads(sample_path.read_text())["as_of"][:10])

    t = time.perf_counter()
    loaded = await load_demo(settings, today, reset=True)
    sync_s = time.perf_counter() - t
    history = await add_daily_history(a.days, today)

    registry = build_registry(settings)
    from app.mcp.servers import build_services
    gw = Gateway(registry, settings.model_copy(update={"rate_limit_per_minute": 100000}), build_services(settings))
    tools = await time_tools(gw, a.runs)
    t = time.perf_counter()
    radar = await run_check(GatewayReader(gw, RADAR_JOB), settings, today)
    radar_s = time.perf_counter() - t
    async with session_scope() as session:
        n = await session.scalar(text("SELECT count(*) FROM app.project"))
    result = {"projects": n, "snapshots_added": history, "load_and_sync_s": round(sync_s, 1),
              "radar_check_s": round(radar_s, 1),
              "radar_findings": radar.get("findings") if isinstance(radar, dict) else None, "tools": tools}
    (HERE / "results.json").write_text(json.dumps(result, indent=2, default=str) + "\n")
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(main())
