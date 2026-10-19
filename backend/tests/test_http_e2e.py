"""End to end: a real gateway process over Streamable HTTP, a real MCP client."""

import json
import os
import socket
import subprocess
import sys
import time

import httpx
import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

from app.db import session_scope
from app.mcp.servers import build_registry
from tests.conftest import BACKEND, DEV_TOKENS, TEST_DB_URL, make_settings


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def start_gateway(port: int) -> subprocess.Popen:
    env = {**os.environ, "APP_ENV": "test", "DATABASE_URL": TEST_DB_URL, "DEV_TOKENS": json.dumps(DEV_TOKENS),
           "SOURCE_MODE": "mock", "REGISTRY_CACHE_SECONDS": "0"}
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(port), "--log-level", "warning"],
        cwd=BACKEND, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    for _ in range(100):
        try:
            if httpx.get(f"http://127.0.0.1:{port}/readyz", timeout=1).status_code == 200:
                return proc
        except httpx.HTTPError:
            pass
        time.sleep(0.1)
    proc.kill()
    raise RuntimeError("gateway did not start: " + (proc.stdout.read().decode() if proc.stdout else ""))


async def mcp_session(url: str, token: str):
    hc = httpx2.AsyncClient(headers={"Authorization": f"Bearer {token}"})
    return hc, Client(streamable_http_client(url, http_client=hc))


async def test_gateway_over_http():
    port = free_port()
    proc = start_gateway(port)
    base = f"http://127.0.0.1:{port}"
    try:
        # No token, or an unknown one: no MCP session at all.
        assert httpx.post(f"{base}/jira/mcp").status_code == 401
        assert httpx.post(f"{base}/jira/mcp", headers={"Authorization": "Bearer nope"}).status_code == 401

        # The owner turns on two JIRA tools.
        registry = build_registry(make_settings())
        async with session_scope() as session:
            await registry.sync(session)
            for tool in ("list_projects", "get_project"):
                await registry.set_status(session, "jira", tool, "on", by="tests")

        hc, client = await mcp_session(f"{base}/jira/mcp", "t-adapter")
        async with hc, client as c:
            tools = sorted(t.name for t in (await c.list_tools()).tools)
            assert tools == ["get_project", "list_projects"]  # the other five are off
            r = await c.call_tool("get_project", {"key": "CHL-DP-LOYAL02", "fields": ["name", "percent_done"]})
            assert not r.is_error
            assert r.structured_content == {"name": "CHL-DP-LOYAL02 Loyalty App v3", "percent_done": 41}
            r = await c.call_tool("get_sprints", {"key": "CHL-DP-LOYAL02"})
            assert r.is_error and "switched off" in r.content[0].text

        hc, client = await mcp_session(f"{base}/jira/mcp", "t-radar")
        async with hc, client as c:
            assert (await c.list_tools()).tools == []  # agents never see source tools
            r = await c.call_tool("list_projects", {})
            assert r.is_error and "Agent callers may not use this tool" in r.content[0].text

        assert httpx.get(f"{base}/healthz").json() == {"status": "ok"}
    finally:
        proc.terminate()
        proc.wait(timeout=10)
