"""Source servers through the guard: only the adapter (and admins) may read
trackers, and a failed source comes back as a clear error."""

from app.db import session_scope
from app.mcp.guard import Gateway
from app.mcp.servers import build_registry, build_services
from tests.conftest import ADAPTER, ADMIN, RADAR, VIEWER, make_settings


async def gateway_with_sources_on() -> Gateway:
    settings = make_settings()
    registry = build_registry(settings)
    async with session_scope() as session:
        await registry.sync(session)
        for source in ("jira", "openproject", "multica"):
            for tool in registry.servers[source].tools:
                await registry.set_status(session, source, tool, "on", by="tests")
    return Gateway(registry, settings, build_services(settings))


async def test_every_source_tool_is_read_only_and_limited_to_adapter_and_admin():
    registry = build_registry(make_settings())
    for source in ("jira", "openproject", "multica"):
        for spec in registry.servers[source].tools.values():
            assert spec.read_only
            assert spec.callers == {"service", "human"}
            assert spec.roles == {"adapter", "admin"}


async def test_adapter_reads_jira():
    gw = await gateway_with_sources_on()
    r = await gw.call(ADAPTER, "jira", "list_projects", {"fields": ["count", "projects[].name"]})
    assert r.outcome == "ok"
    assert r.value["count"] == 5
    assert {"name": "CHL-DP-POS03 POS Integration"} in r.value["projects"]

    r = await gw.call(ADAPTER, "jira", "get_milestones", {"key": "CHL-DP-POS03"})
    assert r.value["milestones"][0]["name"] == "Vendor contract signed"


async def test_agents_and_viewers_cannot_read_trackers_directly():
    gw = await gateway_with_sources_on()
    assert (await gw.call(RADAR, "jira", "list_projects", {})).outcome == "denied"
    r = await gw.call(VIEWER, "openproject", "list_projects", {})
    assert r.outcome == "denied" and "Missing role" in r.message


async def test_admin_can_check_live_source_data():
    gw = await gateway_with_sources_on()
    assert (await gw.call(ADMIN, "openproject", "get_project", {"key": "CHL-IT-DWH04"})).outcome == "ok"


async def test_failed_source_returns_a_clear_error():
    gw = await gateway_with_sources_on()
    r = await gw.call(ADAPTER, "multica", "list_projects", {})
    assert r.outcome == "error"
    assert "Multica" in r.message and "401" in r.message


async def test_unknown_project_key_is_an_error():
    gw = await gateway_with_sources_on()
    r = await gw.call(ADAPTER, "jira", "get_project", {"key": "NOPE"})
    assert r.outcome == "error" and "no project NOPE" in r.message
