"""The live Multica connector, replayed from made-up answers shaped like the real API
(tests/recorded/multica.json), and a full sync through Admin set-up."""

from datetime import date

import httpx
import pytest
from sqlalchemy import select, text

from app.adapter.readers import GatewayReader
from app.adapter import sync
from app.adapter.seed import seed
from app.adapter.sync import sync_all
from app.connectors import SOURCES
from app.connectors import fields as fm
from app.connectors import multica
from app.connectors.base import SourceUnavailable
from app.connectors.http import ReadOnlyHttpClient
from app.connectors.live import LiveConnector
from app.db import session_scope
from app.mcp.guard import Gateway
from app.mcp.identity import Directory
from app.mcp.servers import build_registry
from app.models.app import Milestone, NonCompliant, Project, RawPull, Source, TaskSummary
from app.secretstore import LocalStore
from tests.conftest import ADAPTER, ADMIN, make_settings
from tests.test_live_connectors import Replay


@pytest.fixture(autouse=True)
def small_pages(monkeypatch):
    monkeypatch.setattr(multica, "PAGE", 2)  # the recorded issues come in three pages of at most two


def connector(**field_overrides) -> tuple[multica.MulticaConnector, Replay]:
    rec = Replay("multica.json")
    client = ReadOnlyHttpClient("Multica", rec.base_url, multica.auth_headers("mul_test"), transport=rec.transport(), max_retries=0)
    return multica.MulticaConnector(client, base_url=rec.base_url, fields=fm.MulticaFields(**field_overrides)), rec


async def test_lists_projects_of_every_workspace_with_a_bearer_token():
    c, rec = connector()
    projects = await c.list_projects()
    assert [p.key for p in projects] == ["w1/p1", "w1/p2", "w1/p3", "w2/p9"]
    assert projects[0].name == "CHL-IT-DAAI-901 Alpha Portal" and projects[0].updated_at.isoformat().startswith("2026-10-18T09:12:44")
    assert rec.seen[0].headers["authorization"] == "Bearer mul_test"
    assert all(r.method == "GET" for r in rec.seen)
    assert {r.url.params["workspace_id"] for r in rec.seen if "workspace_id" in r.url.params} == {"w1", "w2"}


async def test_project_owner_dates_status_and_progress():
    c, _ = connector()
    p = await c.get_project("w1/p1")
    assert (p.status, p.owner) == ("in_progress", "Aye Thu")
    assert (p.start_date, p.end_date) == (date(2026, 3, 1), date(2026, 12, 15))
    assert p.percent_done == 40  # Multica's own count: 2 done (one of them cancelled) of 5
    assert (await c.get_project("w1/p2")).owner == "Helper Bot"  # a lead can be an agent
    archive = await c.get_project("w1/p3")
    assert archive.owner is None and archive.percent_done is None  # no lead, and nothing to divide


async def test_task_counts_treat_done_and_cancelled_as_done():
    c, _ = connector()
    counts = await c.get_task_counts("w1/p1")
    assert (counts.todo, counts.in_progress, counts.done, counts.total) == (2, 1, 2, 5)  # all three pages were read
    assert (await c.get_task_counts("w1/p2")).total == 0


async def test_all_issue_pages_are_requested():
    c, rec = connector()
    await c.get_task_counts("w1/p1")
    offsets = [r.url.params["offset"] for r in rec.seen if r.url.path == "/api/issues"]
    assert offsets == ["0", "2", "4"]


async def test_milestones_come_from_the_select_property_in_option_order():
    c, _ = connector()
    ms = await c.get_milestones("w1/p1")
    assert [(m.name, m.status, m.due_date) for m in ms] == [("Pilot", "done", date(2026, 7, 1)), ("Go live", "open", date(2026, 11, 30))]
    assert await c.get_milestones("w1/p2") == []
    off, _ = connector(milestone_property="")
    assert await off.get_milestones("w1/p1") == []


async def test_sprints_and_links_are_empty_because_multica_has_neither():
    c, _ = connector()
    assert await c.get_sprints("w1/p1") == [] and await c.get_links() == []


async def test_risks_are_off_until_mapped_then_read_from_labelled_issues():
    c, rec = connector()
    assert await c.get_risks() == [] and rec.seen == []  # nothing is even requested
    c, _ = connector(risk_label="risk", likelihood_property="Likelihood", impact_property="Impact")
    risks = await c.get_risks()
    assert [(r.project_key, r.title, r.likelihood, r.impact, r.owner) for r in risks] == [("w1/p1", "Vendor delay", "High", "Medium", "Min Zaw")]
    assert await c.get_risks("w2/p9") == []


async def test_a_workspace_filter_and_a_missing_workspace():
    c, _ = connector(workspaces=["beta"])
    assert [p.key for p in await c.list_projects()] == ["w2/p9"]
    gone, _ = connector(workspaces=["nope"])
    with pytest.raises(SourceUnavailable, match="none of the workspaces"):
        await gone.list_projects()


async def test_bad_keys_and_unknown_projects_are_clear_errors():
    c, _ = connector()
    with pytest.raises(SourceUnavailable, match="not a project key"):
        await c.get_project("p1")
    with pytest.raises(SourceUnavailable, match="was not found"):
        await c.get_project("w1/zzz")


async def test_a_refused_token_is_reported_without_the_token():
    client = ReadOnlyHttpClient("Multica", "https://multica.city.local", multica.auth_headers("mul_secret"), max_retries=0,
                                transport=httpx.MockTransport(lambda r: httpx.Response(401, json={"error": "invalid token"})))
    c = multica.MulticaConnector(client, base_url="https://multica.city.local", fields=fm.MulticaFields())
    with pytest.raises(SourceUnavailable, match="access denied") as e:
        await c.list_projects()
    assert "mul_secret" not in str(e.value)


async def test_the_client_cannot_write():
    c, _ = connector()
    with pytest.raises(Exception, match="read-only"):
        await c.client._client.post("/api/projects", json={"title": "x"})


# -- set up from Admin, then a live sync ------------------------------------------

@pytest.fixture(autouse=True)
async def clean_app(engine):
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE app.source, app.prefix, app.project, app.setting, app.sync_run, app.non_compliant "
                                "RESTART IDENTITY CASCADE"))
    yield


@pytest.fixture
async def gw(tmp_path):
    settings = make_settings(source_mode="live", today="2026-10-19")
    registry = build_registry(settings)
    async with session_scope() as session:
        await registry.sync(session)
        for server in registry.servers.values():
            for tool in server.tools:
                await registry.set_status(session, server.name, tool, "on", by="tests")
    await seed()
    store = LocalStore(tmp_path / "secrets.json")
    rec = Replay("multica.json")
    connectors = {sid: LiveConnector(sid, name, settings, store, transport=rec.transport()) for sid, (name, _) in SOURCES.items()}
    g = Gateway(registry, settings, {"connectors": connectors, "secrets": store, "directory": Directory(settings)})
    g.replay = rec
    return g


async def call(g, tool, args):
    r = await g.call(ADMIN, "admin", tool, args)
    assert r.outcome == "ok", r.message
    return r.value


async def test_live_multica_set_up_in_admin_then_synced(gw):
    await call(gw, "save_source", {"source": "multica", "base_url": "https://multica.city.local", "flavor": "",
                                   "auth_method": "token", "account": "", "secret_ref": "kv://multica-read-token"})
    await call(gw, "set_secret", {"ref": "kv://multica-read-token", "value": "mul_test"})

    # Until a person confirms the field mapping, the tracker is reachable but nothing is read into the app.
    first = await sync_all(GatewayReader(gw, ADAPTER), gw.settings, date(2026, 10, 19), only="multica")
    assert not first.sources[0].ok and "field mapping not confirmed" in " ".join(first.sources[0].errors)

    src = await call(gw, "get_source", {"source": "multica"})
    assert {f["field"] for f in src["fields"]["about"]} >= {"workspaces", "milestone_property", "in_progress_statuses"}
    saved = await call(gw, "save_field_mapping", {"source": "multica", "mapping": src["fields"]["values"], "confirm": True})
    assert saved["confirmed"]

    summary = await sync_all(GatewayReader(gw, ADAPTER), gw.settings, date(2026, 10, 19), only="multica")
    result = summary.sources[0]
    assert result.ok, result.errors
    assert result.projects == 3 and result.non_compliant == 1  # "Ops Sandbox" has no approved prefix

    async with session_scope() as session:
        rows = {p.code: p for p in (await session.scalars(select(Project).where(Project.source_id == "multica"))).all()}
        assert set(rows) == {"CHL-IT-DAAI-901", "CHL-IT-DAAI-902", "CHL-IT-DAAI-903"}
        alpha = rows["CHL-IT-DAAI-901"]
        assert (alpha.name, alpha.owner, alpha.status, alpha.percent_done) == ("Alpha Portal", "Aye Thu", "In progress", 40)
        assert (alpha.start_date, alpha.end_date) == (date(2026, 3, 1), date(2026, 12, 15))
        assert alpha.source_key == "w1/p1" and alpha.team == "AI and Agent Teams"
        assert rows["CHL-IT-DAAI-902"].status == "Not started" and rows["CHL-IT-DAAI-903"].status == "Done"
        assert len((await session.scalars(select(Milestone).where(Milestone.project_id == alpha.id))).all()) == 2
        tasks = await session.get(TaskSummary, alpha.id)
        assert (tasks.todo, tasks.in_progress, tasks.done, tasks.total) == (2, 1, 2, 5)
        assert [n.name_in_tracker for n in (await session.scalars(select(NonCompliant))).all()] == ["Ops Sandbox"]
        assert (await session.get(Source, "multica")).last_status == "ok"
    assert all(r.method == "GET" for r in gw.replay.seen)

    # The night's raw answer is archived once per day, as received, and replaced if the sync runs again.
    async def pulls():
        async with session_scope() as session:
            return (await session.scalars(select(RawPull).where(RawPull.source_id == "multica"))).all()

    (pull,) = await pulls()
    assert pull.projects == 3 and {p["project"]["key"] for p in pull.payload["projects"]} == {"w1/p1", "w1/p2", "w1/p3"}
    assert [r["name"] for r in pull.payload["rejected"]] == ["Ops Sandbox"] and len(pull.payload["listing"]) == 4
    assert "match" not in pull.payload["projects"][0]
    await sync_all(GatewayReader(gw, ADAPTER), gw.settings, date(2026, 10, 19), only="multica")
    assert len(await pulls()) == 1


async def test_old_pulls_are_pruned_and_a_failed_source_archives_nothing(gw):
    old = date(2026, 1, 1)
    async with session_scope() as session:
        await sync.archive_pull(session, "multica", old, [], [], [], [], [])
        await sync.archive_pull(session, "multica", date.today(), [], [], [], [], [])
    async with session_scope() as session:
        days = [p.pulled_on for p in (await session.scalars(select(RawPull))).all()]
    assert days == [date.today()]  # the January row is older than the retention window
    failed = await sync_all(GatewayReader(gw, ADAPTER), gw.settings, date(2026, 10, 19), only="multica")  # no address set up yet
    assert not failed.sources[0].ok
    async with session_scope() as session:
        assert [p.pulled_on for p in (await session.scalars(select(RawPull))).all()] == [date.today()]
