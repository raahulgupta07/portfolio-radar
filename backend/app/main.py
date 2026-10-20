"""The City MCP Gateway service.

    uvicorn app.main:app --port 8000

Each registry server is served at /<name>/mcp (Streamable HTTP). /healthz and
/readyz are for the container platform.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from mcp.server.transport_security import TransportSecuritySettings
from sqlalchemy import text

from app.db import get_engine, session_scope
from app.localadmin import ROLES, LocalAdmin
from app.mcp.guard import Gateway
from app.mcp import agents
from app.mcp.identity import Directory, TokenResolver
from app.mcp.registry import Registry
from app.mcp.servers import build_registry, build_services
from app.mcp.transport import RequireToken, build_mcp_server
from app.models.mcp import McpCall
from app.settings import Settings, get_settings
from app.teams.endpoint import TeamsBot

log = logging.getLogger("mcp.gateway")


def create_app(settings: Settings | None = None, registry: Registry | None = None,
               services: dict[str, Any] | None = None) -> FastAPI:
    settings = settings or get_settings()
    registry = registry or build_registry(settings)
    directory = Directory(settings)
    services = dict(services if services is not None else build_services(settings))
    services.setdefault("directory", directory)
    gateway = Gateway(registry, settings, services)
    local_admin = LocalAdmin(settings)
    resolver = TokenResolver(settings, directory=directory, local_admin=local_admin)
    security = TransportSecuritySettings(
        allowed_hosts=settings.mcp_allowed_hosts, allowed_origins=settings.mcp_allowed_origins)

    mcp_servers = {name: build_mcp_server(gateway, name, resolver) for name in registry.servers}

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        async with session_scope() as session:
            report = await registry.sync(session)
        for key in report["new"]:
            log.warning("New tool %s is OFF until its owner turns it on", key)
        for key in report["review"]:
            log.warning("Tool %s changed and waits for owner review", key)
        await agents.refresh(directory)

        async def keep_fresh() -> None:
            # Agents and SSO rules saved in Admin on another copy of the gateway.
            while True:
                await asyncio.sleep(settings.identity_refresh_seconds)
                try:
                    await agents.refresh(directory)
                except Exception:  # noqa: BLE001  keep the last good rules
                    log.exception("could not refresh agents and SSO rules")

        refresher = asyncio.create_task(keep_fresh())
        try:
            async with AsyncExitStack() as stack:
                for srv in mcp_servers.values():
                    await stack.enter_async_context(srv.session_manager.run())
                yield
        finally:
            refresher.cancel()

    app = FastAPI(title="City MCP Gateway", version="0.1.0", lifespan=lifespan)
    app.state.gateway = gateway
    app.state.registry = registry

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz")
    async def readyz() -> JSONResponse:
        try:
            async with get_engine().connect() as conn:
                await conn.execute(text("select 1"))
        except Exception as e:  # noqa: BLE001
            return JSONResponse({"status": "not ready", "error": type(e).__name__}, status_code=503)
        return JSONResponse({"status": "ready", "servers": sorted(registry.servers)})

    @app.get("/auth/local")
    async def local_enabled() -> dict[str, bool]:
        """Whether the superadmin sign-in is on (the web app shows its form only then)."""
        return {"enabled": local_admin.enabled}

    @app.post("/auth/local")
    async def local_sign_in(request: Request) -> JSONResponse:
        """Superadmin sign-in with name and password. Called by the web app's server, never by browsers."""
        try:
            body = await request.json()
            username, password = str(body.get("username", ""))[:100], str(body.get("password", ""))[:200]
        except ValueError:
            return JSONResponse({"error": "bad request"}, status_code=400)
        client = (request.headers.get("x-forwarded-for") or (request.client.host if request.client else "?")).split(",")[0].strip()
        locked = local_admin.enabled and local_admin.locked(client)
        token = None if locked else local_admin.sign_in(username, password, client)
        outcome, reason = ("ok", None) if token else ("denied", "locked for 15 minutes" if locked else "wrong name or password")
        async with session_scope() as session:
            session.add(McpCall(caller_kind="human", caller_id=(f"local:{username}" if username else "local:?")[:200],
                                server="auth", tool="local_sign_in", outcome=outcome, reason=reason,
                                args=json.dumps({"client": client[:60]}), duration_ms=0))
        if not token:
            msg = "Too many tries. Wait 15 minutes." if locked else "Wrong name or password."
            return JSONResponse({"error": msg}, status_code=429 if locked else 401)
        return JSONResponse({"access_token": token, "expires_in": 60 * settings.superadmin_session_minutes,
                             "id": local_admin.caller_id, "roles": sorted(ROLES)})

    teams_bot = TeamsBot(gateway)

    @app.post("/teams/messages")
    async def teams_messages(request: Request) -> Response:
        """Messages from Microsoft Teams (two-way chat with Radar). Checked against Microsoft's token."""
        return await teams_bot.handle(request)

    for name, srv in mcp_servers.items():
        http_app = srv.streamable_http_app(
            streamable_http_path="/mcp", stateless_http=True, json_response=True, transport_security=security)
        app.mount(f"/{name}", RequireToken(http_app, resolver))

    return app


def __getattr__(name: str):
    # `uvicorn app.main:app` builds the app on first use, so importing this module stays cheap.
    if name == "app":
        global app
        app = create_app()
        return app
    raise AttributeError(name)
