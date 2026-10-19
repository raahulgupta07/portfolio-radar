"""Phase 4: /portfolio, /admin and /omni through the guard, on synced sample data."""

from datetime import date

import pytest
from sqlalchemy import select, text

from app.adapter.readers import GatewayReader
from app.adapter.seed import seed
from app.adapter.sync import sync_all
from app.connectors import SOURCES
from app.connectors.mock import MockConnector
from app.db import session_scope
from app.mcp.guard import Gateway
from app.mcp.servers import build_registry
from app.models.mcp import McpCall
from tests.conftest import ADAPTER, ADMIN, BACKEND, RADAR, VIEWER, make_settings

SAMPLE = BACKEND.parent / "design" / "sample-data.json"


@pytest.fixture(autouse=True)
async def clean_app(engine):
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE app.source, app.prefix, app.agent_run, app.setting RESTART IDENTITY CASCADE"))
    yield


@pytest.fixture
async def gw() -> Gateway:
    settings = make_settings(today="2026-10-19")
    registry = build_registry(settings)
    async with session_scope() as session:
        await registry.sync(session)
        for server in registry.servers.values():
            for tool in server.tools:
                await registry.set_status(session, server.name, tool, "on", by="tests")
    await seed()
    up = {sid: MockConnector(sid, SAMPLE, force_up=True) for sid in SOURCES}
    await sync_all(GatewayReader(Gateway(registry, settings, {"connectors": up}), ADAPTER), settings, date(2026, 10, 18))
    real = {sid: MockConnector(sid, SAMPLE) for sid in SOURCES}
    gateway = Gateway(registry, settings, {"connectors": real})
    await sync_all(GatewayReader(gateway, ADAPTER), settings, date(2026, 10, 19))
    return gateway


async def ok(gw: Gateway, caller, server, tool, args=None):
    r = await gw.call(caller, server, tool, args or {})
    assert r.outcome == "ok", r.message
    return r.value


async def test_overview_has_everything_the_screen_needs(gw):
    o = await ok(gw, VIEWER, "portfolio", "get_overview")
    assert {t["label"]: t["count"] for t in o["tiles"]} == {"On track": 6, "At risk": 2, "Off track": 1, "Done": 1}
    multica = next(s for s in o["sources"] if s["id"] == "multica")
    assert multica["stale"] and multica["projects"] == 3 and "401" in multica["error"]
    assert o["next_milestones"][0]["short"] == "POS03" and o["next_milestones"][0]["overdue"]
    assert len(o["projects"]) == 10
    assert all(p["stale"] == (p["source"] == "multica") for p in o["projects"])


async def test_filters_and_search(gw):
    assert (await ok(gw, VIEWER, "portfolio", "list_projects", {"health": "at_risk"}))["count"] == 2
    assert (await ok(gw, VIEWER, "portfolio", "list_projects", {"source": "openproject"}))["count"] == 3
    found = await ok(gw, VIEWER, "portfolio", "list_projects", {"q": "loyal"})
    assert [p["code"] for p in found["projects"]] == ["CHL-DP-LOYAL02"]
    r = await gw.call(VIEWER, "portfolio", "list_projects", {"health": "purple"})
    assert r.outcome == "error"


async def test_project_detail_with_evidence_and_links(gw):
    p = await ok(gw, VIEWER, "portfolio", "get_project", {"code": "chl-dp-loyal02"})
    assert p["health"] == "at_risk"
    assert p["health_reasons"] == ["Waits for Off-track project CHL-DP-POS03"]
    assert p["waits_for"][0]["short"] == "POS03"
    assert p["tasks"]["total"] == 40 and p["source_url"]
    assert p["source_info"]["name"] == "JIRA" and p["synced_at"]
    r = await gw.call(VIEWER, "portfolio", "get_project", {"code": "CHL-NOPE-01"})
    assert r.outcome == "error" and "No project" in r.message


async def test_roadmap_risks_dependencies(gw):
    road = await ok(gw, VIEWER, "portfolio", "get_roadmap")
    assert road["today"] == "2026-10-19" and len(road["projects"]) == 10
    assert len(road["dependencies"]) == 3
    risks = await ok(gw, VIEWER, "portfolio", "get_risks")
    assert [c["label"] for c in risks["matrix"]["High"]["High"]] == ["R5 POS03"]
    assert risks["risks"][0]["title"] == "Vendor contract delayed"  # sorted by score
    gaps = {e["tag"] for e in risks["strategy"] if e["gap"]}
    assert gaps == {"Preferred Business Partner", "Homegrown Champion"}
    deps = (await ok(gw, VIEWER, "portfolio", "get_dependencies"))["dependencies"]
    assert deps[0]["blocked"] and "4 days late" in deps[0]["note"]
    assert "days of buffer" in deps[1]["note"]
    assert any(e["tag"] == "Innovative Market Leader" for e in risks["strategy"])


async def test_viewers_and_agents_cannot_use_admin(gw):
    for caller in (VIEWER, RADAR):
        r = await gw.call(caller, "admin", "get_settings", {})
        assert r.outcome == "denied"


async def test_admin_settings_are_validated_and_saved(gw):
    bad = await gw.call(ADMIN, "admin", "update_settings", {"changes": {"sync_time": "25:00"}})
    assert bad.outcome == "error" and "HH:MM" in bad.message
    unknown = await gw.call(ADMIN, "admin", "update_settings", {"changes": {"self_destruct": True}})
    assert unknown.outcome == "error" and "Unknown settings" in unknown.message
    saved = await ok(gw, ADMIN, "admin", "update_settings", {"changes": {"overdue_days": 10, "sync_time": "03:30"}})
    assert saved["overdue_days"] == 10
    assert (await ok(gw, ADMIN, "admin", "get_settings"))["sync_time"] == "03:30"


async def test_new_thresholds_apply_on_the_next_sync(gw):
    await ok(gw, ADMIN, "admin", "update_settings", {"changes": {"overdue_days": 10}})
    summary = await ok(gw, ADMIN, "admin", "run_sync", {"source": "jira"})
    # POS03 is On hold with an overdue milestone, so it stays Off track whatever the day count.
    assert summary["health"]["CHL-DP-POS03"] == "off_track"


async def test_adding_a_prefix_picks_up_projects_on_the_next_sync(gw):
    await ok(gw, ADMIN, "admin", "add_prefix", {"value": "CHLIT-", "description": "Old style"})
    await ok(gw, ADMIN, "admin", "run_sync", {"source": "openproject"})
    nc = await ok(gw, ADMIN, "admin", "get_non_compliant")
    assert "CHLIT-ANALYTICS Sales Insights" not in [n["name_in_tracker"] for n in nc["projects"]]
    bad = await gw.call(ADMIN, "admin", "add_prefix", {"value": "lower-"})
    assert bad.outcome == "error"


async def test_sync_log_and_test_source(gw):
    log = await ok(gw, ADMIN, "admin", "get_sync_log", {"source": "multica"})
    assert [r["result"] for r in log["runs"]] == ["failed", "ok"]
    assert (await ok(gw, ADMIN, "admin", "test_source", {"source": "multica"}))["ok"] is False
    assert (await ok(gw, ADMIN, "admin", "test_source", {"source": "jira"}))["projects_found"] == 5


async def test_admin_turns_tools_off_and_it_takes_effect(gw):
    await ok(gw, ADMIN, "admin", "set_tool_status", {"server": "portfolio", "tool": "get_risks", "status": "off"})
    r = await gw.call(VIEWER, "portfolio", "get_risks", {})
    assert r.outcome == "denied" and "switched off" in r.message


async def test_omni_shows_only_what_the_caller_may_use(gw):
    radar_servers = {s["server"] for s in (await ok(gw, RADAR, "omni", "discover_server", {"query": ""}))["servers"]}
    assert "portfolio" in radar_servers
    assert not radar_servers & {"admin", "jira", "openproject", "multica"}
    admin_servers = {s["server"] for s in (await ok(gw, ADMIN, "omni", "discover_server", {"query": "", "limit": 20}))["servers"]}
    assert {"admin", "jira", "portfolio"} <= admin_servers

    tools = await ok(gw, RADAR, "omni", "discover_tools", {"server": "portfolio"})
    assert "get_overview" in [t["tool"] for t in tools["tools"]]
    schema = await ok(gw, RADAR, "omni", "get_tool_schema", {"server": "portfolio", "tool": "get_project"})
    assert "code" in schema["input_schema"]["properties"]


async def test_omni_invoke_goes_through_the_guard_and_is_audited(gw):
    r = await ok(gw, RADAR, "omni", "invoke_tool", {
        "server": "portfolio", "tool": "list_projects", "arguments": {"health": "off_track"},
        "projection": ["projects[].code"]})
    assert r["result"] == {"projects": [{"code": "CHL-DP-POS03"}]}
    denied = await gw.call(RADAR, "omni", "invoke_tool", {"server": "admin", "tool": "run_sync", "arguments": {}})
    assert denied.outcome == "error" and "Agent callers" in denied.message
    async with session_scope() as session:
        rows = (await session.scalars(select(McpCall).where(McpCall.caller_id == "radar").order_by(McpCall.id))).all()
    pairs = [(c.server, c.tool, c.outcome) for c in rows]
    assert ("portfolio", "list_projects", "ok") in pairs
    assert ("admin", "run_sync", "denied") in pairs


# -- PDF one-pagers (FR-16) --------------------------------------------------------

async def test_project_and_portfolio_one_pagers_are_single_page_pdfs(gw):
    import base64
    import re

    for tool, args, name in (("get_project_pdf", {"code": "chl-dp-pos03"}, "CHL-DP-POS03-one-pager.pdf"),
                             ("get_overview_pdf", {}, "portfolio-2026-10-19.pdf")):
        r = await ok(gw, VIEWER, "portfolio", tool, args)
        pdf = base64.b64decode(r["content_base64"])
        assert r["filename"] == name and pdf.startswith(b"%PDF") and r["bytes"] == len(pdf)
        assert len(re.findall(rb"/Type /Page\b", pdf)) == 1
    agent = await gw.call(RADAR, "portfolio", "get_overview_pdf", {})
    assert agent.outcome == "denied"  # PDFs are for people; agents read the data tools
    missing = await gw.call(VIEWER, "portfolio", "get_project_pdf", {"code": "NOPE-1"})
    assert missing.outcome == "error" and "No project" in missing.message
