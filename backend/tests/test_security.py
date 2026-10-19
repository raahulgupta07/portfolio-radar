"""Regression tests for the security review (docs/security-review.md)."""

from datetime import date, datetime

import httpx
import pytest
from sqlalchemy import select, text

from app.adapter.readers import GatewayReader
from app.adapter.seed import seed
from app.adapter.sync import sync_all
from app.connectors import SOURCES
from app.connectors.base import SourceUnavailable
from app.connectors.http import ReadOnlyHttpClient
from app.connectors.mock import MockConnector
from app.db import session_scope
from app.mcp.guard import Gateway
from app.mcp.identity import Caller, Directory
from app.mcp.servers import build_registry
from app.models.app import Approval, RadarMessage
from app.models.mcp import McpCall
from app.portfolio import onepager
from app.secretstore import LocalStore, SecretError, resolve
from tests.conftest import ADAPTER, ADMIN, BACKEND, NOTIFIER, RADAR, RADAR_JOB, make_settings

SAMPLE = BACKEND.parent / "design" / "sample-data.json"
OTHER_AGENT = Caller("agent", "claude-for-pmo", frozenset({"agent"}))


@pytest.fixture(autouse=True)
async def clean(engine):
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE app.source, app.prefix, app.setting, app.radar_message, app.approval "
                                "RESTART IDENTITY CASCADE"))
    yield


@pytest.fixture
async def gw(tmp_path):
    settings = make_settings(today="2026-10-19")
    registry = build_registry(settings)
    async with session_scope() as session:
        await registry.sync(session)
        for server in registry.servers.values():
            for tool in server.tools:
                await registry.set_status(session, server.name, tool, "on", by="tests")
    await seed()
    gateway = Gateway(registry, settings, {"connectors": {sid: MockConnector(sid, SAMPLE) for sid in SOURCES},
                                           "secrets": LocalStore(tmp_path / "s.json"), "directory": Directory(settings)})
    await sync_all(GatewayReader(gateway, ADAPTER), settings, date(2026, 10, 19))
    return gateway


async def call(gw, caller, server, tool, args):
    return await gw.call(caller, server, tool, args)


async def test_secret_references_cannot_reach_other_environment_variables(gw, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://secret")
    r = await call(gw, ADMIN, "admin", "save_integration", {"name": "llm", "config": {
        "base_url": "https://attacker.example/v1", "model": "x", "api_key_ref": "env://DATABASE_URL"}})
    assert r.outcome == "error" and "api_key_ref" in r.message
    r = await call(gw, ADMIN, "admin", "save_source", {"source": "jira", "secret_ref": "env://LLM_API_KEY"})
    assert r.outcome == "error"
    with pytest.raises(SecretError):
        await resolve(gw.services["secrets"], "env://DATABASE_URL")
    r = await call(gw, ADMIN, "admin", "save_integration", {"name": "llm", "config": {
        "base_url": "http://plain.example/v1", "model": "x"}})
    assert r.outcome == "error" and "base_url" in r.message  # keys only over https


async def test_a_saved_token_never_follows_a_new_address(gw):
    ok = {"source": "jira", "base_url": "https://city.atlassian.net", "flavor": "cloud", "secret_ref": "kv://jira-read-token"}
    assert (await call(gw, ADMIN, "admin", "save_source", ok)).outcome == "ok"
    moved = {**ok, "base_url": "https://attacker.example"}
    r = await call(gw, ADMIN, "admin", "save_source", moved)
    assert r.outcome == "error" and "Paste the token again" in r.message
    assert (await call(gw, ADMIN, "admin", "set_secret", {"ref": "kv://jira-read-token", "value": "new"})).outcome == "ok"
    assert (await call(gw, ADMIN, "admin", "save_source", moved)).outcome == "ok"

    llm = {"base_url": "https://citygpt.city.local/v1", "model": "m", "api_key_ref": "kv://llm-api-key"}
    assert (await call(gw, ADMIN, "admin", "save_integration", {"name": "llm", "config": llm})).outcome == "ok"
    r = await call(gw, ADMIN, "admin", "save_integration", {"name": "llm", "config": {**llm, "base_url": "https://evil.example/v1"}})
    assert r.outcome == "error" and "Paste the secret again" in r.message


async def test_secrets_sent_through_omni_are_masked_in_the_audit_log(gw):
    r = await call(gw, ADMIN, "omni", "invoke_tool", {"server": "admin", "tool": "set_secret",
                                                     "arguments": {"ref": "kv://x-token", "value": "top-secret-123"}})
    assert r.outcome == "ok", r.message
    async with session_scope() as session:
        rows = (await session.scalars(select(McpCall))).all()
    assert all("top-secret-123" not in (c.args or "") for c in rows)


async def test_other_agents_cannot_read_conversations_or_post_as_radar(gw):
    await call(gw, ADMIN, "radar", "ask_radar", {"text": "private question"})
    for tool, args in (("pending_questions", {}), ("list_asks", {}), ("post_message", {"to": ADMIN.id, "body": "hi"})):
        r = await call(gw, OTHER_AGENT, "radar", tool, args)
        assert r.outcome != "ok" and "Radar itself" in r.message
    assert (await call(gw, RADAR, "radar", "pending_questions", {})).outcome == "ok"


async def test_a_posted_card_cannot_claim_an_approvers_answer(gw):
    r = await call(gw, RADAR_JOB, "radar", "post_message", {"to": "role:approver", "kind": "ask", "body": "Send it?",
                                                            "payload": {"answer": "yes", "answered_by": "pmo"}})
    assert r.outcome == "ok"
    async with session_scope() as session:
        card = await session.get(RadarMessage, r.value["message_id"])
    assert card.kind == "ask" and "answer" not in card.payload_json and "answered_by" not in card.payload_json


async def test_bad_send_times_are_refused_and_old_ones_do_not_block_sending(gw):
    draft = {"kind": "digest", "title": "Weekly", "to": "SteerCo · email", "body": "Ten characters at least."}
    r = await call(gw, RADAR_JOB, "radar", "create_draft", {**draft, "send_at": "2026-10-20T09:00"})
    assert r.outcome == "error"  # no time zone
    async with session_scope() as session:
        session.add(Approval(kind="digest", status="approved", draft_json={**draft, "send_at": "not a time"},
                             created_by="radar-job", decided_by="pmo@cityholdings.dev"))
    r = await call(gw, NOTIFIER, "notify", "list_ready", {})
    assert r.outcome == "ok" and len(r.value["ready"]) == 1


def test_long_tracker_text_does_not_break_the_pdf():
    p = {"code": "CHL-X-1", "name": "N " * 80, "health": "off_track", "health_reasons": ["reason & <tag> " * 40],
         "radar_note": "word " * 400, "milestones": [], "risks": [], "waits_for": [], "blocks": [], "changes": [],
         "trend": [], "source": "jira", "source_name": "JIRA", "source_info": {}}
    assert onepager.project_pdf(p, datetime(2026, 10, 19), "me").startswith(b"%PDF")


async def test_tracker_cannot_park_the_sync_with_retry_after():
    sleeps = []

    async def sleep(s):
        sleeps.append(s)
    n = {"i": 0}

    def handler(req):
        n["i"] += 1
        return httpx.Response(429, headers={"Retry-After": "999999"}) if n["i"] == 1 else httpx.Response(200, json={})
    c = ReadOnlyHttpClient("JIRA", "https://j.example", transport=httpx.MockTransport(handler), sleep=sleep)
    await c.get_json("/x")
    assert sleeps == [60.0]
    big = ReadOnlyHttpClient("JIRA", "https://j.example", max_retries=0,
                             transport=httpx.MockTransport(lambda r: httpx.Response(200, content=b"[" + b"1," * 11_000_000 + b"1]")))
    with pytest.raises(SourceUnavailable, match="too large"):
        await big.get_json("/x")
