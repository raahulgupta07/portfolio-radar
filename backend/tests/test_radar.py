"""Phases 6-8: Radar's checks, conversation, asks, drafts, approvals, sending."""

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
from app.models.app import Approval
from app.radar import writer
from app.radar.assistant import answer_pending
from app.radar.job import act_on_answers, run_check
from app.radar.notifier import run_notifier
from app.radar.rules import check
from tests.conftest import ADAPTER, ADMIN, APPROVER, BACKEND, NOTIFIER, RADAR, RADAR_JOB, VIEWER, make_settings

SAMPLE = BACKEND.parent / "design" / "sample-data.json"
TODAY = date(2026, 10, 19)


@pytest.fixture(autouse=True)
async def clean_app(engine):
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE app.source, app.prefix, app.agent_run, app.setting, app.radar_message, "
                                "app.approval, app.radar_memory RESTART IDENTITY CASCADE"))
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
    gateway = Gateway(registry, settings, {"connectors": {sid: MockConnector(sid, SAMPLE) for sid in SOURCES}})
    await sync_all(GatewayReader(gateway, ADAPTER), settings, TODAY)
    return gateway


async def ok(gw, caller, server, tool, args=None):
    r = await gw.call(caller, server, tool, args or {})
    assert r.outcome == "ok", r.message
    return r.value


# -- rules ---------------------------------------------------------------------

def test_rules_word_findings_like_the_design():
    projects = [
        {"code": "CHL-DP-POS03", "short": "POS03", "name": "POS Integration", "health": "off_track",
         "health_reasons": ["Milestone 'Vendor contract signed' is 4 days overdue (due 15 Oct)"], "owner": "X",
         "source": "jira", "source_name": "JIRA", "next_milestone": "Vendor contract signed",
         "next_milestone_due": "2026-10-15", "percent_done": 30, "milestones": 1, "milestones_without_date": 0,
         "blocks": ["LOYAL02"], "updated": "2026-10-12"},
        {"code": "CHL-IT-DAAI-AGT04", "short": "AGT04", "name": "Agent Ops Console", "health": "at_risk",
         "health_reasons": ["No owner"], "owner": None, "source": "multica", "source_name": "Multica",
         "milestones": 0, "milestones_without_date": 0, "updated": "2026-10-18"},
    ]
    sources = [{"id": "multica", "name": "Multica", "stale": True, "last_good_sync_at": "2026-10-17T19:30:00+00:00",
                "error": "401", "projects": 3}, {"id": "jira", "name": "JIRA", "stale": False}]
    texts = [f.text for f in check(projects, sources, TODAY)]
    assert texts[0] == "POS03 milestone 4 days overdue"
    assert "Multica data is 1 day old" in texts
    assert "AGT04 has no owner" in texts and "AGT04 has no milestone dates" in texts
    # At risk only because of data gaps: no "slipping" finding.
    assert not any(t.startswith("AGT04 slipping") for t in texts)


# -- nightly check -------------------------------------------------------------

async def test_nightly_check_posts_findings_asks_and_digest(gw):
    result = await run_check(GatewayReader(gw, RADAR_JOB), gw.settings, TODAY, force_digest=True)
    # 4, not 5: no snapshot from last week, so no "turned At risk this week" finding.
    assert result["findings"] == 4 and result["asks"] == 1 and result["drafts"] == 1

    conv = await ok(gw, VIEWER, "radar", "get_conversation")
    kinds = [m["kind"] for m in conv["messages"]]
    assert kinds[:5] == ["divider", "radar", "health", "findings", "dep"]
    assert "ask" not in kinds and "approval" not in kinds  # viewers do not see approvers' items
    assert "Evidence" not in conv["messages"][1]["body"] and conv["messages"][1]["payload"]["evidence"]

    pmo = await ok(gw, APPROVER, "radar", "get_conversation")
    assert {w["type"] for w in pmo["waiting"]} == {"ask", "approval"}
    assert pmo["status"]["mood"] == "asking"

    overview = await ok(gw, VIEWER, "portfolio", "get_overview", {"fields": ["radar"]})
    assert overview["radar"]["count"] == 4
    assert overview["radar"]["items"][0]["text"] == "POS03 milestone 4 days overdue"


async def test_second_check_keeps_first_seen_and_does_not_ask_twice(gw):
    r1 = await run_check(GatewayReader(gw, RADAR_JOB), gw.settings, TODAY)
    r2 = await run_check(GatewayReader(gw, RADAR_JOB), gw.settings, TODAY)
    assert r1["new"] and r2["new"] == []
    assert r2["asks"] == 0
    f = await ok(gw, VIEWER, "radar", "get_findings")
    assert all(x["first_seen_at"] < f["run"]["ended_at"] for x in f["findings"])


async def test_radar_off_in_admin_skips_the_check(gw):
    await ok(gw, ADMIN, "admin", "update_settings", {"changes": {"radar_on": False}})
    assert (await run_check(GatewayReader(gw, RADAR_JOB), gw.settings, TODAY)) == {"skipped": True}


# -- asking and approving ------------------------------------------------------

async def test_yes_to_a_nudge_question_makes_a_draft_not_a_message(gw):
    await run_check(GatewayReader(gw, RADAR_JOB), gw.settings, TODAY)
    pmo = await ok(gw, APPROVER, "radar", "get_conversation")
    ask = next(w for w in pmo["waiting"] if w["type"] == "ask")

    denied = await gw.call(VIEWER, "radar", "answer_ask", {"message_id": ask["message_id"], "answer": "yes"})
    assert denied.outcome == "denied"
    await ok(gw, APPROVER, "radar", "answer_ask", {"message_id": ask["message_id"], "answer": "yes"})
    again = await gw.call(APPROVER, "radar", "answer_ask", {"message_id": ask["message_id"], "answer": "no"})
    assert again.outcome == "error" and "Already answered" in again.message

    assert await act_on_answers(GatewayReader(gw, RADAR_JOB)) == 1
    assert await act_on_answers(GatewayReader(gw, RADAR_JOB)) == 0  # only once
    drafts = (await ok(gw, APPROVER, "radar", "list_approvals", {"status": "pending"}))["approvals"]
    nudge = next(d for d in drafts if d["kind"] == "nudge")
    assert nudge["project"] == "CHL-DP-POS03" and "Edit here" in nudge["body"]


async def test_only_a_human_approver_can_decide(gw):
    await run_check(GatewayReader(gw, RADAR_JOB), gw.settings, TODAY, force_digest=True)
    digest = (await ok(gw, APPROVER, "radar", "list_approvals"))["approvals"][0]
    for caller in (RADAR, RADAR_JOB, VIEWER, ADMIN):
        r = await gw.call(caller, "radar", "decide_approval", {"approval_id": digest["id"], "decision": "approve"})
        assert r.outcome == "denied", caller
    async with session_scope() as session:
        assert (await session.get(Approval, digest["id"])).status == "pending"


async def test_approved_draft_is_sent_once_and_rejected_never(gw):
    await run_check(GatewayReader(gw, RADAR_JOB), gw.settings, TODAY, force_digest=True)
    digest = (await ok(gw, APPROVER, "radar", "list_approvals"))["approvals"][0]
    notifier = GatewayReader(gw, NOTIFIER)

    assert await run_notifier(notifier, gw.settings) == 0  # pending: nothing to send
    await ok(gw, APPROVER, "radar", "decide_approval",
             {"approval_id": digest["id"], "decision": "approve", "body": digest["body"] + "\nEdited by PMO."})
    # Digest waits for its send time (Friday 16:00), so it is not sent on Monday.
    assert await run_notifier(notifier, gw.settings) == 0
    async with session_scope() as session:
        a = await session.get(Approval, digest["id"])
        a.draft_json = {**a.draft_json, "send_at": None}
    assert await run_notifier(notifier, gw.settings) == 1
    assert await run_notifier(notifier, gw.settings) == 0
    async with session_scope() as session:
        a = await session.get(Approval, digest["id"])
        assert a.sent_at is not None and a.draft_json["send_result"]["channels"] == ["dev outbox"]
        assert a.draft_json["body"].endswith("Edited by PMO.")

    rejected = await gw.call(APPROVER, "radar", "decide_approval", {"approval_id": digest["id"], "decision": "reject"})
    assert rejected.outcome == "error" and "already approved" in rejected.message


async def test_notifier_cannot_see_pending_drafts_or_mark_them(gw):
    await run_check(GatewayReader(gw, RADAR_JOB), gw.settings, TODAY, force_digest=True)
    digest = (await ok(gw, APPROVER, "radar", "list_approvals"))["approvals"][0]
    r = await gw.call(NOTIFIER, "notify", "mark_sent", {"approval_id": digest["id"], "ok": True})
    assert r.outcome == "error" and "Only approved" in r.message
    assert (await gw.call(RADAR, "notify", "list_ready", {})).outcome == "denied"


# -- questions -----------------------------------------------------------------

async def test_questions_get_answers_with_evidence(gw):
    await ok(gw, VIEWER, "radar", "ask_radar", {"text": "How is POS03 doing?"})
    await ok(gw, VIEWER, "radar", "ask_radar", {"text": "What is off track?"})
    other = await ok(gw, APPROVER, "radar", "ask_radar", {"text": "Is the sync ok?"})
    assert await answer_pending(GatewayReader(gw, RADAR), gw.settings) == 3

    conv = await ok(gw, VIEWER, "radar", "get_conversation")
    answers = [m for m in conv["messages"] if m["kind"] == "radar"]
    assert "POS03 POS Integration is off track" in answers[0]["body"]
    assert "JIRA · CHL-DP-POS03" in answers[0]["payload"]["evidence"]
    assert answers[1]["body"].startswith("1 project off track")
    assert all(m["state"] != "pending" for m in conv["messages"] if m["kind"] == "me")
    assert not any(m.get("reply_to") == other["message_id"] for m in conv["messages"])  # not someone else's


async def test_memory_is_visible_and_removable(gw):
    m = await ok(gw, RADAR, "radar", "remember", {"text": "The digest puts decisions first"})
    assert (await ok(gw, VIEWER, "radar", "get_conversation"))["memory"][0]["text"] == "The digest puts decisions first"
    assert (await gw.call(RADAR, "radar", "forget", {"id": m["id"]})).outcome == "denied"
    await ok(gw, VIEWER, "radar", "forget", {"id": m["id"]})


async def test_writer_falls_back_to_template_when_llm_is_unreachable():
    settings = make_settings(llm_base_url="http://127.0.0.1:9/v1", llm_model="any")
    assert await writer.polish(settings, "task", "facts", "template text") == "template text"


async def test_people_cannot_post_as_radar(gw):
    r = await gw.call(VIEWER, "radar", "post_message", {"to": "*", "body": "I am Radar"})
    assert r.outcome == "denied"
    r = await gw.call(VIEWER, "radar", "create_draft", {"kind": "nudge", "title": "x x x", "to": "all", "body": "0123456789"})
    assert r.outcome == "denied"
