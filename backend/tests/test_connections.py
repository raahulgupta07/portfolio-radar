"""Admin → Connections and Agents: set up every connection from the app,
through /admin/mcp, with secrets kept out of the database and the audit log."""

import json
from datetime import date

import httpx
import pytest
from sqlalchemy import select, text

from app.adapter.readers import GatewayReader
from app.adapter.seed import seed
from app.adapter.sync import sync_all
from app.connectors import SOURCES
from app.connectors.mock import MockConnector
from app.db import session_scope
from app.mcp.guard import Gateway
from app.mcp.identity import Caller, Directory
from app.mcp.servers import build_registry
from app.models.app import Setting, Source
from app.models.mcp import McpCall
from app.radar.runtime import _channels, _llm
from app.secretstore import LocalStore
from tests.conftest import ADAPTER, ADMIN, BACKEND, NOTIFIER, RADAR, VIEWER, make_settings

SAMPLE = BACKEND.parent / "design" / "sample-data.json"
APP_ID = "3f9b2d41-8e0c-4a77-b1f2-56c0d9e1a7aa"
TENANT = "11111111-2222-3333-4444-555555555555"


class Outside:
    """Stands in for Entra ID, the LLM and Teams; records what was sent."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if "openid-configuration" in request.url.path:
            return httpx.Response(200, json={"issuer": f"https://login.microsoftonline.com/{TENANT}/v2.0"})
        if request.url.path.endswith("/chat/completions"):
            ok = request.headers.get("authorization") == "Bearer sk-test"
            return httpx.Response(200 if ok else 401, json={"choices": [{"message": {"content": "OK"}}]})
        if request.url.host == "teams.example":
            return httpx.Response(200, text="1")
        return httpx.Response(404)


@pytest.fixture(autouse=True)
async def clean_app(engine):
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE app.source, app.prefix, app.agent_run, app.setting, mcp.agent "
                                "RESTART IDENTITY CASCADE"))
    yield


@pytest.fixture
def outside() -> Outside:
    return Outside()


@pytest.fixture
async def gw(tmp_path, outside) -> Gateway:
    settings = make_settings(today="2026-10-19")
    registry = build_registry(settings)
    async with session_scope() as session:
        await registry.sync(session)
        for server in registry.servers.values():
            for tool in server.tools:
                await registry.set_status(session, server.name, tool, "on", by="tests")
    await seed()
    sent: list[tuple] = []
    services = {
        "connectors": {sid: MockConnector(sid, SAMPLE) for sid in SOURCES},
        "secrets": LocalStore(tmp_path / "secrets.json"),
        "directory": Directory(settings),
        "http_transport": httpx.MockTransport(outside),
        "smtp_send": lambda cfg, password, to: sent.append((cfg.smtp_host, password, to)),
    }
    gateway = Gateway(registry, settings, services)
    gateway.sent_mail = sent
    await sync_all(GatewayReader(gateway, ADAPTER), settings, date(2026, 10, 19))
    return gateway


async def ok(gw: Gateway, caller, server, tool, args=None):
    r = await gw.call(caller, server, tool, args or {})
    assert r.outcome == "ok", r.message
    return r.value


async def fails(gw: Gateway, caller, server, tool, args=None) -> str:
    r = await gw.call(caller, server, tool, args or {})
    assert r.outcome != "ok"
    return r.message


# -- secrets ---------------------------------------------------------------------

async def test_secret_is_stored_never_returned_and_never_audited(gw, tmp_path):
    await ok(gw, ADMIN, "admin", "set_secret", {"ref": "kv://jira-read-token", "value": "s3cr3t-jira"})
    assert json.loads((tmp_path / "secrets.json").read_text()) == {"jira-read-token": "s3cr3t-jira"}
    assert oct((tmp_path / "secrets.json").stat().st_mode)[-3:] == "600"

    await ok(gw, ADMIN, "admin", "save_source", {"source": "jira", "base_url": "https://cityholdings.atlassian.net",
                                                 "flavor": "cloud", "auth_method": "api_token",
                                                 "account": "svc-portfolio-read@city.com",
                                                 "secret_ref": "kv://jira-read-token"})
    conns = await ok(gw, ADMIN, "admin", "get_connections")
    jira = next(s for s in conns["sources"] if s["id"] == "jira")
    assert jira["secret_ref"] == "kv://jira-read-token" and jira["secret_set"] is True
    assert "s3cr3t" not in json.dumps(conns)

    async with session_scope() as session:
        rows = (await session.scalars(select(McpCall).where(McpCall.tool == "set_secret"))).all()
        db_dump = json.dumps([r.value for r in (await session.scalars(select(Setting))).all()])
    assert rows and all("s3cr3t" not in (r.args or "") and "[secret]" in r.args for r in rows)
    assert "s3cr3t" not in db_dump


async def test_only_admins_can_set_secrets(gw):
    for caller in (VIEWER, RADAR, ADAPTER):
        await fails(gw, caller, "admin", "set_secret", {"ref": "kv://x", "value": "y"})
    msg = await fails(gw, ADMIN, "admin", "set_secret", {"ref": "plain-name", "value": "y"})
    assert "ref" in msg


# -- source trackers -----------------------------------------------------------

async def test_source_settings_are_checked_before_saving(gw):
    assert "https" in await fails(gw, ADMIN, "admin", "save_source", {"source": "jira", "base_url": "http://jira.local"})
    assert "Sign-in" in await fails(gw, ADMIN, "admin", "save_source", {"source": "openproject", "auth_method": "pat"})
    assert "JIRA only" in await fails(gw, ADMIN, "admin", "save_source", {"source": "multica", "flavor": "cloud"})

    await ok(gw, ADMIN, "admin", "save_source", {"source": "jira", "base_url": "https://jira.city.local",
                                                 "flavor": "datacenter", "auth_method": "pat",
                                                 "secret_ref": "kv://jira-pat"})
    src = await ok(gw, ADMIN, "admin", "get_source", {"source": "jira"})
    assert (src["base_url"], src["flavor"], src["auth_method"], src["secret_set"]) == (
        "https://jira.city.local", "datacenter", "pat", False)
    assert {t["tool"] for t in src["tools"]} >= {"list_projects", "get_project"}
    assert src["app_statuses"] == ["Not started", "In progress", "Done", "On hold"]


async def test_check_source_reports_prefixes_and_failures(gw):
    jira = await ok(gw, ADMIN, "admin", "check_source", {"source": "jira"})
    checks = {c["check"]: c for c in jira["checks"]}
    assert jira["ok"] and checks["Match a prefix"]["detail"] == "4"
    assert "Mobile Wallet POC" in checks["Names with no prefix"]["detail"]
    multica = await ok(gw, ADMIN, "admin", "check_source", {"source": "multica"})
    assert not multica["ok"] and "401" in multica["checks"][-1]["detail"]


async def test_status_mapping_from_admin_is_used_by_the_sync(gw):
    src = await ok(gw, ADMIN, "admin", "get_source", {"source": "openproject"})
    default = {m["tracker_status"]: m["app_status"] for m in src["mapping"] if m["from"] == "default"}
    # Take "in progress" out of the default mapping: OpenProject projects using it stop syncing.
    await ok(gw, ADMIN, "admin", "save_status_mapping", {
        "source": "default", "mapping": {k: v for k, v in default.items() if k != "in progress"}})
    check = await ok(gw, ADMIN, "admin", "check_source", {"source": "openproject"})
    assert check["unmapped"] == ["In progress"]
    s = await sync_all(GatewayReader(gw, ADAPTER), gw.settings, date(2026, 10, 19), "openproject")
    assert any("Admin → Connections" in e for e in s.sources[0].errors)
    assert (await ok(gw, ADMIN, "admin", "get_source", {"source": "openproject"}))["unmapped"] == ["In progress"]

    await ok(gw, ADMIN, "admin", "save_status_mapping", {"source": "openproject", "mapping": {"In Progress": "In progress"}})
    assert (await ok(gw, ADMIN, "admin", "get_source", {"source": "openproject"}))["unmapped"] == []
    s = await sync_all(GatewayReader(gw, ADAPTER), gw.settings, date(2026, 10, 19), "openproject")
    assert s.sources[0].ok and not s.sources[0].errors
    await fails(gw, ADMIN, "admin", "save_status_mapping", {"source": "jira", "mapping": {"UAT": "Guessed"}})


# -- outside services ------------------------------------------------------------

async def test_llm_saved_in_admin_is_tested_and_reaches_the_worker(gw, outside):
    services = (await ok(gw, ADMIN, "admin", "get_integrations"))["services"]
    assert services["llm"]["status"] == "rules_only" and not services["llm"]["saved_in_admin"]

    await ok(gw, ADMIN, "admin", "save_integration", {"name": "llm", "config": {
        "provider": "citygpt", "base_url": "https://citygpt.city.local/v1", "model": "city-gpt-4",
        "api_key_ref": "kv://llm-api-key"}})
    services = (await ok(gw, ADMIN, "admin", "get_integrations"))["services"]
    assert services["llm"]["status"] == "secret_missing"
    t = await ok(gw, ADMIN, "admin", "test_integration", {"name": "llm"})
    assert not t["ok"] and "API key" in t["detail"]

    await ok(gw, ADMIN, "admin", "set_secret", {"ref": "kv://llm-api-key", "value": "sk-test"})
    t = await ok(gw, ADMIN, "admin", "test_integration", {"name": "llm"})
    assert t["ok"] and "OK" in t["detail"]
    assert outside.requests[-1].url == "https://citygpt.city.local/v1/chat/completions"

    # The worker reads the settings through MCP and the key from the store.
    rs = await _llm(GatewayReader(gw, RADAR), gw.settings, gw.services["secrets"])
    assert (rs.llm_base_url, rs.llm_model, rs.llm_api_key) == ("https://citygpt.city.local/v1", "city-gpt-4", "sk-test")


async def test_teams_and_email_tests_and_notifier_channels(gw, outside):
    await ok(gw, ADMIN, "admin", "set_secret", {"ref": "kv://teams-webhook", "value": "https://teams.example/hook/1"})
    await ok(gw, ADMIN, "admin", "save_integration", {"name": "teams", "config": {
        "webhook_ref": "kv://teams-webhook", "channel": "#steerco-portfolio"}})
    t = await ok(gw, ADMIN, "admin", "test_integration", {"name": "teams"})
    assert t["ok"] and outside.requests[-1].url.host == "teams.example"
    assert "approves" in json.loads(outside.requests[-1].content)["text"]

    assert "not an email" in await fails(gw, ADMIN, "admin", "save_integration", {"name": "email", "config": {
        "smtp_host": "smtp.office365.com", "recipients": ["steerco"]}})
    await ok(gw, ADMIN, "admin", "save_integration", {"name": "email", "config": {
        "smtp_host": "smtp.office365.com", "username": "radar@city.com", "password_ref": "kv://smtp-password",
        "recipients": ["steerco@city.com"]}})
    await ok(gw, ADMIN, "admin", "set_secret", {"ref": "kv://smtp-password", "value": "pw"})
    t = await ok(gw, ADMIN, "admin", "test_integration", {"name": "email"})
    assert t["ok"] and gw.sent_mail[-1] == ("smtp.office365.com", "pw", ADMIN.id)

    ns = await _channels(GatewayReader(gw, NOTIFIER), gw.settings, gw.services["secrets"])
    assert ns.teams_webhook_url == "https://teams.example/hook/1"
    assert (ns.smtp_host, ns.smtp_password, ns.notify_email_to) == ("smtp.office365.com", "pw", ["steerco@city.com"])


async def test_sso_needs_an_admin_group_and_applies_at_once(gw):
    msg = await fails(gw, ADMIN, "admin", "save_integration", {"name": "sso", "config": {
        "tenant_id": TENANT, "audience": "api://city-mcp-gateway",
        "groups": [{"group_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee", "roles": ["viewer"]}]}})
    assert "admin role" in msg
    await ok(gw, ADMIN, "admin", "save_integration", {"name": "sso", "config": {
        "tenant_id": TENANT, "audience": "api://city-mcp-gateway",
        "groups": [{"group_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee", "name": "IT", "roles": ["admin"]}]}})
    sso = gw.services["directory"].sso
    assert sso.tenant_id == TENANT and sso.group_roles == {"aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee": ("admin",)}
    t = await ok(gw, ADMIN, "admin", "test_integration", {"name": "sso"})
    assert t["ok"], t


# -- agents ------------------------------------------------------------------------

async def test_agent_set_up_in_admin_is_limited_to_its_servers(gw):
    assert "roles" in await fails(gw, ADMIN, "admin", "save_agent", {
        "name": "Sneaky", "app_id": APP_ID, "roles": ["approver"], "servers": ["portfolio"]})
    assert "Not a server" in await fails(gw, ADMIN, "admin", "save_agent", {
        "name": "Sneaky", "app_id": APP_ID, "servers": ["admin"]})
    assert "another name" in await fails(gw, ADMIN, "admin", "save_agent", {
        "name": "Radar", "app_id": APP_ID, "servers": ["portfolio"]})

    saved = await ok(gw, ADMIN, "admin", "save_agent", {"name": "Claude for PMO", "app_id": APP_ID.upper(),
                                                         "servers": ["portfolio"], "rate_limit": 3})
    caller = gw.services["directory"].app(APP_ID)
    assert caller == Caller("agent", "claude-for-pmo", frozenset({"agent"}), frozenset({"portfolio"}), 3)

    assert (await gw.call(caller, "portfolio", "get_overview", {})).outcome == "ok"
    assert "may not use the radar server" in (await gw.call(caller, "radar", "get_findings", {})).message
    found = await ok(gw, caller, "omni", "discover_server", {"query": ""})
    assert {s["server"] for s in found["servers"]} == {"portfolio", "system"}
    assert "Too many" in (await gw.call(caller, "portfolio", "get_overview", {})).message  # 3 per minute

    preview = await ok(gw, ADMIN, "admin", "preview_agent", {"id": saved["id"]})
    assert {s["server"] for s in preview["servers"]} == {"portfolio", "omni", "system"}
    assert "radar.decide_approval" in preview["never_allowed"]

    agents = await ok(gw, ADMIN, "admin", "list_agents")
    assert [a["caller_id"] for a in agents["agents"]] == ["claude-for-pmo"]
    assert agents["agents"][0]["calls_today"] >= 3
    assert {b["caller_id"] for b in agents["built_in"]} == {"radar", "radar-job", "adapter", "notifier", "teams"}

    await ok(gw, ADMIN, "admin", "set_agent_enabled", {"id": saved["id"], "enabled": False})
    assert gw.services["directory"].app(APP_ID) is None


async def test_connections_overview_counts(gw):
    c = await ok(gw, ADMIN, "admin", "get_connections")
    assert c["summary"]["servers"] == len(gw.registry.servers)
    assert c["summary"]["tools"] == c["summary"]["tools_on"] == len(gw.registry.all_tools())
    assert c["summary"]["secret_store"] == "local" and c["summary"]["source_mode"] == "mock"
    assert [s["id"] for s in c["sources"]] == ["jira", "openproject", "multica"]
    assert next(s for s in c["sources"] if s["id"] == "jira")["tools"]["on"] == 7
    assert {s["server"] for s in c["servers"]} >= {"portfolio", "radar", "admin", "notify", "omni", "system"}
    assert set(c["services"]) == {"sso", "llm", "teams", "email"}
    async with session_scope() as session:
        assert (await session.get(Source, "jira")).enabled


# -- Admin → People ------------------------------------------------------------------

async def test_people_are_recorded_and_admins_can_add_roles_or_block(gw):
    await ok(gw, VIEWER, "system", "whoami", {"name": "Viewer Person"})
    people = (await ok(gw, ADMIN, "admin", "list_people"))["people"]
    assert [(p["id"], p["name"], p["sso_roles"]) for p in people] == [(VIEWER.id, "Viewer Person", ["viewer"])]
    assert "admin" in await fails(gw, VIEWER, "admin", "list_people")  # admins only

    saved = await ok(gw, ADMIN, "admin", "save_person", {"id": VIEWER.id, "extra_roles": ["approver"], "note": "PMO cover"})
    assert saved["roles"] == ["approver", "viewer"]
    rule = gw.services["directory"].people[VIEWER.id]
    assert rule.extra_roles == {"approver"} and not rule.blocked
    await ok(gw, ADMIN, "admin", "save_person", {"id": "new.starter@cityholdings.dev", "extra_roles": ["viewer"]})
    await ok(gw, ADMIN, "admin", "save_person", {"id": VIEWER.id, "blocked": True})
    assert gw.services["directory"].people[VIEWER.id].blocked
    assert "yourself" in await fails(gw, ADMIN, "admin", "save_person", {"id": ADMIN.id, "blocked": True})


async def test_keycloak_sso_settings_take_group_names(gw):
    msg = await fails(gw, ADMIN, "admin", "save_integration", {"name": "sso", "config": {
        "provider": "entra", "tenant_id": TENANT, "audience": "a", "groups": [{"group_id": "portfolio-admins", "roles": ["admin"]}]}})
    assert "group object ID" in msg
    await ok(gw, ADMIN, "admin", "save_integration", {"name": "sso", "config": {
        "provider": "keycloak", "issuer": "https://sso.city.local/realms/city", "audience": "portfolio-radar-gateway",
        "user_apps": ["portfolio-radar-web"],
        "groups": [{"group_id": "/portfolio-admins", "name": "Admins", "roles": ["admin"]}]}})
    sso = gw.services["directory"].sso
    assert (sso.provider, sso.issuer, sso.group_roles) == ("keycloak", "https://sso.city.local/realms/city",
                                                            {"/portfolio-admins": ("admin",)})


async def test_openrouter_needs_only_a_key_and_a_model(gw, outside):
    await ok(gw, ADMIN, "admin", "set_secret", {"ref": "kv://openrouter-key", "value": "sk-test"})
    await ok(gw, ADMIN, "admin", "save_integration", {"name": "llm", "config": {
        "provider": "openrouter", "model": "vendor/some-model", "api_key_ref": "kv://openrouter-key"}})
    services = (await ok(gw, ADMIN, "admin", "get_integrations"))["services"]
    assert services["llm"]["config"]["base_url"] == "https://openrouter.ai/api/v1"
    t = await ok(gw, ADMIN, "admin", "test_integration", {"name": "llm"})
    assert t["ok"], t
    sent = outside.requests[-1]
    assert sent.url == "https://openrouter.ai/api/v1/chat/completions" and sent.headers["x-title"] == "Portfolio Radar"
    rs = await _llm(GatewayReader(gw, RADAR), gw.settings, gw.services["secrets"])
    assert (rs.llm_provider, rs.llm_base_url, rs.llm_api_key) == ("openrouter", "https://openrouter.ai/api/v1", "sk-test")
