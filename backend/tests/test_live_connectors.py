"""Phase 13: live JIRA (Cloud and Data Center) and OpenProject connectors,
replayed from recorded responses (tests/recorded), and the set-up path in
Admin: address, token, field mapping, check, sync."""

import json
from datetime import date
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select, text

from app.adapter.readers import GatewayReader
from app.adapter.seed import seed
from app.adapter.sync import sync_all
from app.connectors import SOURCES
from app.connectors import fields as fm
from app.connectors.base import SourceUnavailable
from app.connectors.http import ReadOnlyHttpClient
from app.connectors.jira import JiraConnector, auth_headers
from app.connectors.live import LiveConnector
from app.connectors.openproject import OpenProjectConnector
from app.db import session_scope
from app.mcp.guard import Gateway
from app.mcp.identity import Directory
from app.mcp.servers import build_registry
from app.models.app import Dependency, Milestone, Project, Risk, Source, Sprint, TaskSummary
from app.models.mcp import McpCall
from app.secretstore import LocalStore
from tests.conftest import ADAPTER, ADMIN, make_settings

RECORDED = Path(__file__).parent / "recorded"
ASPIRATIONS = make_settings().strategy_aspirations


class Replay:
    """Answers GET requests from a recorded file and keeps every request it saw."""

    def __init__(self, name: str) -> None:
        data = json.loads((RECORDED / name).read_text())
        self.base_url = data["base_url"]
        self.entries = data["requests"]
        self.seen: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.seen.append(request)
        params = request.url.params
        for e in self.entries:
            if e["path"] == request.url.path and all(v in params.get(k, "") for k, v in e.get("params", {}).items()):
                return httpx.Response(e.get("status", 200), json=e["json"])
        return httpx.Response(404, json={"errorMessages": [f"not recorded: {request.url}"]})

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self)


def jira(flavor: str, **field_overrides) -> tuple[JiraConnector, Replay]:
    rec = Replay(f"jira-{flavor}.json")
    client = ReadOnlyHttpClient("JIRA", rec.base_url, auth_headers(flavor, "svc-radar@city.com", "tok-123"),
                                transport=rec.transport(), max_retries=0)
    fields = fm.JiraFields(strategy_field="customfield_10100", likelihood_field="customfield_10200",
                           impact_field="customfield_10201", **field_overrides)
    return JiraConnector(client, flavor=flavor, base_url=rec.base_url, fields=fields, aspirations=ASPIRATIONS), rec


def openproject(**field_overrides) -> tuple[OpenProjectConnector, Replay]:
    rec = Replay("openproject.json")
    client = ReadOnlyHttpClient("OpenProject", rec.base_url, {"Authorization": "Basic x"}, transport=rec.transport(), max_retries=0)
    fields = fm.OpenProjectFields(owner_field="customField2", strategy_field="customField4",
                                  likelihood_field="customField7", impact_field="customField8", **field_overrides)
    return OpenProjectConnector(client, base_url=rec.base_url, fields=fields, aspirations=ASPIRATIONS,
                                today=lambda: date(2026, 10, 19)), rec


# -- JIRA Cloud ------------------------------------------------------------------

async def test_jira_cloud_lists_projects_across_pages_with_basic_auth():
    c, rec = jira("cloud")
    projects = await c.list_projects()
    assert [p.key for p in projects] == ["DAAI", "DP", "SBX"]
    assert projects[0].url == "https://city.atlassian.net/browse/DAAI"
    assert projects[0].updated_at.isoformat().startswith("2026-10-18T09:12:44")
    assert rec.seen[0].headers["authorization"].startswith("Basic ")
    assert all(r.method == "GET" for r in rec.seen)


async def test_jira_cloud_project_reads_the_anchor_issue_and_counts_tasks():
    c, _ = jira("cloud")
    p = await c.get_project("DAAI")
    assert (p.status, p.owner, p.team) == ("In Progress", "Aye Aye", "Data Team")
    assert (p.start_date, p.end_date) == (date(2026, 3, 1), date(2026, 12, 15))
    assert p.percent_done == 50  # 5 done of 10, the To Do count spans two pages
    assert p.strategy_tag == "Innovative Market Leader"


async def test_jira_cloud_versions_sprints_links_and_risks():
    c, _ = jira("cloud")
    ms = await c.get_milestones("DAAI")
    assert [(m.name, m.status) for m in ms] == [("Beta", "open"), ("Alpha", "done")]  # archived left out
    sprints = await c.get_sprints("DAAI")
    assert sprints[0].name == "DAAI Sprint 12" and sprints[0].end_date == date(2026, 10, 27)
    assert sprints[1].goal is None
    links = await c.get_links()
    assert [(link.from_key, link.to_key) for link in links] == [("DAAI", "DP")]  # deduped, same-project and "relates" skipped
    risks = await c.get_risks()
    assert [(r.project_key, r.likelihood, r.impact) for r in risks] == [("DAAI", "High", "Medium")]  # "Severe" is not guessed


async def test_jira_risks_are_not_read_until_their_fields_are_mapped():
    c, rec = jira("cloud")
    c.f = c.f.model_copy(update={"likelihood_field": ""})
    assert await c.get_risks() == []
    assert rec.seen == []


async def test_jira_status_from_category_needs_no_anchor():
    c, _ = jira("cloud", anchor_jql="", status_from="category")
    p = await c.get_project("DAAI")
    assert p.status == "Data Team" and p.start_date is None


async def test_jira_missing_anchor_is_a_clear_error():
    c, _ = jira("cloud", anchor_jql='project = "{key}" AND issuetype = Initiative')
    with pytest.raises(SourceUnavailable, match="no anchor issue for DAAI"):
        await c.get_project("DAAI")


async def test_jira_cloud_needs_the_account_email():
    with pytest.raises(SourceUnavailable, match="email"):
        auth_headers("cloud", "", "tok")


# -- JIRA Data Center ------------------------------------------------------------

async def test_jira_datacenter_uses_v2_bearer_and_totals():
    c, rec = jira("datacenter")
    assert [p.key for p in await c.list_projects()] == ["DAAI"]
    counts = await c.get_task_counts("DAAI")
    assert (counts.todo, counts.in_progress, counts.done, counts.total) == (4, 1, 15, 20)
    links = await c.get_links()  # two pages by startAt
    assert [(link.from_key, link.to_key) for link in links] == [("DAAI", "CRM"), ("OPS", "DAAI")]
    assert rec.seen[0].headers["authorization"] == "Bearer tok-123"
    assert all(r.url.path.startswith("/rest/api/2/") for r in rec.seen)


# -- OpenProject -----------------------------------------------------------------

async def test_openproject_project_status_owner_dates_and_progress():
    c, _ = openproject()
    assert [p.key for p in await c.list_projects()] == ["cdp", "crm"]
    p = await c.get_project("cdp")
    assert (p.status, p.owner, p.url) == ("On track", "Thida Win", "https://op.city.local/projects/cdp")
    assert (p.start_date, p.end_date) == (date(2026, 2, 2), date(2026, 12, 20))
    assert p.percent_done == 50 and p.strategy_tag == "Benchmark of Excellence"
    counts = await c.get_task_counts("cdp")
    assert (counts.todo, counts.in_progress, counts.done) == (4, 2, 6)


async def test_openproject_milestones_sprints_links_risks():
    c, _ = openproject()
    ms = await c.get_milestones("cdp")
    assert [(m.name, m.status, m.due_date) for m in ms] == [("Go-live", "open", date(2026, 12, 1)),
                                                             ("Design sign-off", "done", date(2026, 6, 30))]
    sprints = await c.get_sprints("cdp")
    assert [(s.name, s.state) for s in sprints] == [("Sprint 8", "active"), ("Sprint 9", "future")]
    links = await c.get_links()
    assert [(link.from_key, link.to_key) for link in links] == [("cdp", "crm")]  # same-project relation skipped
    risks = await c.get_risks()
    assert [(r.project_key, r.title, r.likelihood) for r in risks] == [("cdp", "Vendor delay", "High")]


# -- set up from Admin, then a live sync ------------------------------------------

@pytest.fixture(autouse=True)
async def clean_app(engine):
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE app.source, app.prefix, app.project, app.setting, app.sync_run "
                                "RESTART IDENTITY CASCADE"))
    yield


@pytest.fixture
async def live_gw(tmp_path):
    settings = make_settings(source_mode="live", today="2026-10-19")
    registry = build_registry(settings)
    async with session_scope() as session:
        await registry.sync(session)
        for server in registry.servers.values():
            for tool in server.tools:
                await registry.set_status(session, server.name, tool, "on", by="tests")
    await seed()
    store = LocalStore(tmp_path / "secrets.json")
    rec = Replay("jira-cloud.json")
    connectors = {sid: LiveConnector(sid, name, settings, store, transport=rec.transport())
                  for sid, (name, _) in SOURCES.items()}
    gw = Gateway(registry, settings, {"connectors": connectors, "secrets": store, "directory": Directory(settings)})
    gw.replay = rec
    return gw


async def call(gw, tool, args):
    r = await gw.call(ADMIN, "admin", tool, args)
    assert r.outcome == "ok", r.message
    return r.value


async def test_live_jira_set_up_in_admin_then_synced(live_gw):
    gw = live_gw
    await call(gw, "save_source", {"source": "jira", "base_url": "https://city.atlassian.net", "flavor": "cloud",
                                   "auth_method": "api_token", "account": "svc-radar@city.com",
                                   "secret_ref": "kv://jira-read-token"})
    await call(gw, "set_secret", {"ref": "kv://jira-read-token", "value": "tok-123"})

    # Before the mapping is confirmed: the tracker is reached, but nothing is read into the app.
    check = await call(gw, "check_source", {"source": "jira"})
    by = {c["check"]: c for c in check["checks"]}
    assert by["Tracker reached"]["ok"] and by["Projects found"]["detail"] == "3"
    assert not by["Field mapping"]["ok"]
    assert "Team sandbox" in by["Names with no prefix"]["detail"]
    summary = await sync_all(GatewayReader(gw, ADAPTER), gw.settings, date(2026, 10, 19))
    jira_result = next(s for s in summary.sources if s.source_id == "jira")
    assert not jira_result.ok and "field mapping not confirmed" in " ".join(jira_result.errors)

    src = await call(gw, "get_source", {"source": "jira"})
    assert src["fields"]["confirmed_by"] is None
    assert {f["field"] for f in src["fields"]["about"]} >= {"anchor_jql", "status_from", "percent_done"}
    fields = {**src["fields"]["values"], "strategy_field": "customfield_10100",
              "likelihood_field": "customfield_10200", "impact_field": "customfield_10201"}
    saved = await call(gw, "save_field_mapping", {"source": "jira", "mapping": fields, "confirm": True})
    assert saved["confirmed"]

    summary = await sync_all(GatewayReader(gw, ADAPTER), gw.settings, date(2026, 10, 19))
    by_source = {s.source_id: s for s in summary.sources}
    assert by_source["jira"].ok, by_source["jira"].errors
    assert not by_source["multica"].ok and "no address set" in by_source["multica"].errors[0]  # not set up in Admin yet
    async with session_scope() as session:
        daai = await session.scalar(select(Project).where(Project.code == "CHL-IT-DAAI-014"))
        assert daai is not None and daai.percent_done == 50 and daai.status == "In progress"
        assert daai.strategy_tag == "Innovative Market Leader"
        assert len((await session.scalars(select(Milestone).where(Milestone.project_id == daai.id))).all()) == 2
        assert (await session.scalars(select(Sprint).where(Sprint.project_id == daai.id))).first() is not None
        assert (await session.get(TaskSummary, daai.id)) is not None
        assert len((await session.scalars(select(Dependency))).all()) == 1
        assert [r.title for r in (await session.scalars(select(Risk))).all()] == ["Vendor API not ready"]
        jira = await session.get(Source, "jira")
        assert jira.last_status == "ok"
        calls = (await session.scalars(select(McpCall))).all()
    assert all(r.method == "GET" for r in gw.replay.seen)
    assert all("tok-123" not in (c.args or "") for c in calls)


async def test_changing_the_mapping_without_confirming_stops_the_live_sync(live_gw):
    gw = live_gw
    await call(gw, "save_field_mapping", {"source": "jira", "mapping": fm.JiraFields().model_dump(), "confirm": True})
    await call(gw, "save_field_mapping", {"source": "jira", "mapping": {**fm.JiraFields().model_dump(), "end_date_field": "customfield_1"}})
    async with session_scope() as session:
        assert not (await fm.load(session, "jira")).confirmed
    r = await gw.call(ADMIN, "admin", "save_field_mapping", {"source": "jira", "mapping": {"start_date_field": "bad field!"}})
    assert r.outcome != "ok" and "start_date_field" in r.message
