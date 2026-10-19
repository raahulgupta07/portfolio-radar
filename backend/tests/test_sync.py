"""Phase 3: prefix rule, status mapping, health rule, the nightly sync,
stale sources, non-compliant names, links and snapshots."""

from datetime import date

import pytest
from sqlalchemy import func, select, text

from app.adapter.readers import GatewayReader
from app.adapter.seed import seed
from app.adapter.sync import StatusMap, match_prefix, sync_all
from app.connectors import SOURCES
from app.connectors.base import ProjectRef, SourceProject
from app.connectors.mock import MockConnector
from app.db import session_scope
from app.health import (
    AT_RISK,
    DONE,
    OFF_TRACK,
    ON_TRACK,
    MilestoneInfo,
    ProjectInfo,
    Thresholds,
    assess,
    assess_all,
)
from app.mcp.guard import Gateway
from app.mcp.servers import build_registry
from app.models.app import Dependency, NonCompliant, Project, Snapshot, Source, SyncRun
from tests.conftest import ADAPTER, BACKEND, make_settings

TODAY = date(2026, 10, 19)
PREFIXES = ["CHL-DP-", "CHL-IT-", "CHL-IT-DAAI-", "CMHL-IT-"]


@pytest.fixture(autouse=True)
async def clean_app(engine):
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE app.source, app.prefix, app.agent_run RESTART IDENTITY CASCADE"))
    yield


# -- prefix rule ---------------------------------------------------------------

def test_longest_prefix_wins_and_case_is_ignored():
    m = match_prefix("chl-it-daai-gpt03 CityGPT Agents", PREFIXES)
    assert (m.prefix, m.code, m.name) == ("CHL-IT-DAAI-", "CHL-IT-DAAI-GPT03", "CityGPT Agents")
    assert match_prefix("CHL-IT-ERP02 ERP Upgrade", PREFIXES).prefix == "CHL-IT-"


def test_names_without_an_approved_prefix_are_rejected_with_a_reason():
    assert match_prefix("Mobile Wallet POC", PREFIXES).reason == "No prefix"
    assert match_prefix("CHLIT-ANALYTICS Sales Insights", PREFIXES).reason == "Prefix not recognised"
    assert match_prefix("CHL-DP- missing code", PREFIXES).reason == "Prefix not recognised"
    assert match_prefix("", PREFIXES).reason == "No prefix"


def test_status_map_uses_source_section_then_default():
    sm = StatusMap(BACKEND / "config" / "status_map.json")
    assert sm.map("jira", "In Progress") == "In progress"
    assert sm.map("openproject", "Scheduled") == "Not started"
    assert sm.map("jira", "Scheduled") is None  # only mapped for OpenProject
    assert sm.map("multica", "Waiting for Godot") is None


# -- health rule ---------------------------------------------------------------

def info(**kw) -> ProjectInfo:
    base = dict(code="X", status="In progress", start_date=date(2026, 9, 1), end_date=date(2026, 12, 31),
                percent_done=40, owner="Someone", milestones=(MilestoneInfo("M1", date(2026, 11, 30), False),))
    base.update(kw)
    return ProjectInfo(**base)


T = Thresholds()


def test_health_on_track_and_done():
    assert assess(info(), TODAY, T).health == ON_TRACK
    assert assess(info(status="Done", owner=None, milestones=()), TODAY, T).health == DONE


def test_overdue_more_than_three_days_is_off_track_but_three_days_is_not():
    four = info(milestones=(MilestoneInfo("Beta", date(2026, 10, 15), False),))
    three = info(milestones=(MilestoneInfo("Beta", date(2026, 10, 16), False),))
    assert assess(four, TODAY, T).health == OFF_TRACK
    assert assess(three, TODAY, T).health != OFF_TRACK
    assert assess(info(status="On hold", milestones=(MilestoneInfo("Beta", date(2026, 10, 18), False),)),
                  TODAY, T).health == OFF_TRACK


def test_at_risk_reasons():
    behind = assess(info(percent_done=10), TODAY, T)  # ~38% of time used
    assert behind.health == AT_RISK and "points behind" in behind.reasons[0]
    soon = assess(info(percent_done=35, milestones=(MilestoneInfo("Beta", date(2026, 10, 24), False),)), TODAY, T)
    assert any("due in 5 days" in r for r in soon.reasons)
    assert assess(info(owner=None), TODAY, T).reasons == ["No owner"]
    assert assess(info(milestones=()), TODAY, T).reasons == ["No milestone dates"]


def test_waiting_for_an_off_track_project_is_at_risk():
    blocker = info(code="A", milestones=(MilestoneInfo("Late", date(2026, 10, 1), False),))
    waiting = info(code="B", waits_for=("A",))
    res = assess_all([blocker, waiting], TODAY, T)
    assert res["A"].health == OFF_TRACK
    assert res["B"].health == AT_RISK and res["B"].reasons == ["Waits for Off-track project A"]


def test_thresholds_come_from_settings():
    strict = Thresholds.from_settings(make_settings(health_overdue_days=0))
    late = info(milestones=(MilestoneInfo("Beta", date(2026, 10, 18), False),))
    assert assess(late, TODAY, strict).health == OFF_TRACK


# -- the sync ------------------------------------------------------------------

async def reader_with(connectors, settings=None):
    settings = settings or make_settings()
    registry = build_registry(settings)
    async with session_scope() as session:
        await registry.sync(session)
        for sid in SOURCES:
            for tool in registry.servers[sid].tools:
                await registry.set_status(session, sid, tool, "on", by="tests")
    return GatewayReader(Gateway(registry, settings, {"connectors": connectors}), ADAPTER), settings


def mocks(force_up=False):
    path = BACKEND.parent / "design" / "sample-data.json"
    return {sid: MockConnector(sid, path, force_up=force_up) for sid in SOURCES}


async def count(model) -> int:
    async with session_scope() as session:
        return await session.scalar(select(func.count()).select_from(model))


async def test_sync_writes_projects_health_and_snapshots():
    await seed()
    reader, settings = await reader_with(mocks(force_up=True))
    summary = await sync_all(reader, settings, TODAY)
    assert all(s.ok for s in summary.sources)
    assert await count(Project) == 10
    assert summary.health["CHL-DP-POS03"] == OFF_TRACK
    assert summary.health["CHL-DP-LOYAL02"] == AT_RISK
    assert summary.health["CHL-IT-DAAI-AGT04"] == AT_RISK
    assert summary.health["CMHL-IT-BI01"] == DONE
    assert await count(Snapshot) == 10
    assert await count(Dependency) == 3

    async with session_scope() as session:
        pos = await session.scalar(select(Project).where(Project.code == "CHL-DP-POS03"))
        assert pos.prefix == "CHL-DP-" and pos.name == "POS Integration" and pos.status_raw == "On hold"
        assert "4 days overdue" in pos.health_reasons[0]
        nc = (await session.scalars(select(NonCompliant).order_by(NonCompliant.source_id))).all()
        assert [(n.source_id, n.name_in_tracker, n.reason) for n in nc] == [
            ("jira", "Mobile Wallet POC", "No prefix"),
            ("multica", "Chatbot experiments", "No prefix"),
            ("openproject", "CHLIT-ANALYTICS Sales Insights", "Prefix not recognised"),
        ]


async def test_failed_source_keeps_last_good_data_and_others_continue():
    await seed()
    reader, settings = await reader_with(mocks(force_up=True))
    await sync_all(reader, settings, date(2026, 10, 18))

    reader, settings = await reader_with(mocks(force_up=False))
    summary = await sync_all(reader, settings, TODAY)
    by = {s.source_id: s for s in summary.sources}
    assert by["jira"].ok and by["openproject"].ok and not by["multica"].ok
    assert "401" in by["multica"].errors[0]
    assert await count(Project) == 10  # Multica's 3 projects are kept
    async with session_scope() as session:
        multica = await session.get(Source, "multica")
        assert multica.last_status == "failed" and multica.last_good_sync_at is not None
        assert multica.last_good_sync_at < multica.last_sync_at
        runs = (await session.scalars(select(SyncRun).where(SyncRun.source_id == "multica").order_by(SyncRun.id))).all()
        assert [r.result for r in runs] == ["ok", "failed"]


async def test_running_twice_does_not_duplicate_anything():
    await seed()
    reader, settings = await reader_with(mocks(force_up=True))
    await sync_all(reader, settings, TODAY)
    await sync_all(reader, settings, TODAY)
    assert await count(Project) == 10
    assert await count(Dependency) == 3
    assert await count(Snapshot) == 10
    assert await count(NonCompliant) == 3


class OddStatusConnector(MockConnector):
    async def get_project(self, key: str) -> SourceProject:
        p = await super().get_project(key)
        return p.model_copy(update={"status": "Waiting for Godot"}) if key == "CHL-DP-HR05" else p


async def test_unmapped_status_is_reported_not_guessed():
    await seed()
    path = BACKEND.parent / "design" / "sample-data.json"
    conns = mocks(force_up=True)
    conns["jira"] = OddStatusConnector("jira", path)
    reader, settings = await reader_with(conns)
    summary = await sync_all(reader, settings, TODAY)
    jira = next(s for s in summary.sources if s.source_id == "jira")
    assert jira.ok and jira.projects == 3
    assert "status 'Waiting for Godot' has no mapping" in jira.errors[0]


class DuplicateConnector(MockConnector):
    """OpenProject that also has a project named with JIRA's POS03 code."""

    def __init__(self, source_id, path):
        super().__init__(source_id, path, force_up=True)
        self._jira = MockConnector("jira", path, force_up=True)

    async def list_projects(self) -> list[ProjectRef]:
        return await super().list_projects() + [ProjectRef(key="DUP", name="CHL-DP-POS03 POS Integration (copy)")]

    async def get_project(self, key: str) -> SourceProject:
        if key == "DUP":
            return (await self._jira.get_project("CHL-DP-POS03")).model_copy(update={"key": "DUP"})
        return await super().get_project(key)

    async def get_milestones(self, key):
        return await (self._jira.get_milestones("CHL-DP-POS03") if key == "DUP" else super().get_milestones(key))

    async def get_sprints(self, key):
        return await (self._jira.get_sprints("CHL-DP-POS03") if key == "DUP" else super().get_sprints(key))

    async def get_task_counts(self, key):
        return await (self._jira.get_task_counts("CHL-DP-POS03") if key == "DUP" else super().get_task_counts(key))


async def test_same_code_in_two_sources_is_flagged():
    await seed()
    path = BACKEND.parent / "design" / "sample-data.json"
    conns = mocks(force_up=True)
    conns["openproject"] = DuplicateConnector("openproject", path)
    reader, settings = await reader_with(conns)
    summary = await sync_all(reader, settings, TODAY)
    assert summary.duplicates == ["CHL-DP-POS03 in jira and openproject"]


async def test_sync_is_blocked_when_source_tools_are_off():
    await seed()
    settings = make_settings()
    registry = build_registry(settings)
    async with session_scope() as session:
        await registry.sync(session)
    reader = GatewayReader(Gateway(registry, settings, {"connectors": mocks(True)}), ADAPTER)
    summary = await sync_all(reader, settings, TODAY)
    assert not any(s.ok for s in summary.sources)
    assert "switched off" in summary.sources[0].errors[0]
