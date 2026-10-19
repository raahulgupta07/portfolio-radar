"""Connector library: the read-only HTTP client and the mock connector."""

import httpx
import pytest

from app.connectors.base import SourceUnavailable
from app.connectors.http import ReadOnlyHttpClient, ReadOnlyViolation
from app.connectors.mock import MockConnector
from tests.conftest import BACKEND

SAMPLE = BACKEND.parent / "design" / "sample-data.json"


def client(handler, **kw) -> tuple[ReadOnlyHttpClient, list[float]]:
    sleeps: list[float] = []

    async def fake_sleep(s: float) -> None:
        sleeps.append(s)

    c = ReadOnlyHttpClient("JIRA", "https://jira.example.invalid", transport=httpx.MockTransport(handler),
                           sleep=fake_sleep, **kw)
    return c, sleeps


async def test_client_has_no_write_methods_and_blocks_writes_underneath():
    c, _ = client(lambda req: httpx.Response(200, json={}))
    for name in ("post", "put", "patch", "delete", "request"):
        assert not hasattr(c, name)
    for method in ("POST", "PUT", "PATCH", "DELETE"):
        with pytest.raises(ReadOnlyViolation):
            await c._client.request(method, "/rest/api/3/issue")
    await c.aclose()


async def test_get_retries_server_errors_with_backoff():
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        return httpx.Response(503) if calls["n"] < 3 else httpx.Response(200, json={"ok": True})

    c, sleeps = client(handler, backoff_seconds=1.0)
    assert await c.get_json("/x") == {"ok": True}
    assert sleeps == [1.0, 2.0]
    await c.aclose()


async def test_get_honours_retry_after_on_429():
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        return httpx.Response(429, headers={"Retry-After": "7"}) if calls["n"] == 1 else httpx.Response(200, json=[])

    c, sleeps = client(handler)
    assert await c.get_json("/x") == []
    assert sleeps == [7.0]
    await c.aclose()


async def test_auth_failure_is_reported_without_retry():
    c, sleeps = client(lambda req: httpx.Response(401))
    with pytest.raises(SourceUnavailable, match="401 access denied"):
        await c.get_json("/x")
    assert sleeps == []
    await c.aclose()


async def test_gives_up_after_max_retries():
    c, sleeps = client(lambda req: httpx.Response(502), max_retries=2)
    with pytest.raises(SourceUnavailable, match="HTTP 502"):
        await c.get_json("/x")
    assert len(sleeps) == 2
    await c.aclose()


async def test_mock_jira_lists_compliant_and_non_compliant_projects():
    jira = MockConnector("jira", SAMPLE)
    refs = await jira.list_projects()
    names = [r.name for r in refs]
    assert "CHL-DP-POS03 POS Integration" in names
    assert "Mobile Wallet POC" in names  # no prefix: the adapter will report it
    p = await jira.get_project("CHL-DP-POS03")
    assert p.status == "On hold" and p.percent_done == 30


async def test_mock_task_counts_add_up_and_match_percent_done():
    jira = MockConnector("jira", SAMPLE)
    t = await jira.get_task_counts("CHL-DP-LOYAL02")  # 41 % done
    assert t.todo + t.in_progress + t.done == t.total == 40
    assert t.done == 16


async def test_mock_links_and_risks_belong_to_the_source():
    op = MockConnector("openproject", SAMPLE)
    assert [(link.from_key, link.to_key) for link in await op.get_links()] == [("CHL-IT-DWH04", "CHL-IT-DAAI-FC03")]
    jira = MockConnector("jira", SAMPLE)
    assert {r.project_key for r in await jira.get_risks()} <= {"CHL-DP-POS03", "CHL-DP-LOYAL02", "CHL-DP-PORTAL01", "CHL-DP-HR05"}


async def test_failed_source_raises_like_the_expired_multica_token():
    multica = MockConnector("multica", SAMPLE)
    with pytest.raises(SourceUnavailable, match="401 Unauthorized"):
        await multica.list_projects()
