"""The gateway's Teams endpoint: POST /teams/messages (reached through the web
app's /api/teams/messages, which only forwards).

For each message: check Microsoft's token, accept only 1:1 chats from the City
tenant, look up the sender's City account, and pass the text to Radar with
`radar.ask_from_teams` as the `teams` service, so the guard and audit log see it
like any other call. Radar's answer goes back later through the notifier.
"""

from __future__ import annotations

import logging
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app import integrations
from app.db import session_scope
from app.mcp.guard import Gateway
from app.mcp.identity import Caller
from app.secretstore import SecretError, resolve
from app.teams.botframework import BotAuthError, BotConnector, BotTokenVerifier, safe_service_url

log = logging.getLogger("teams")
TEAMS = Caller(kind="service", id="teams", roles=frozenset({"teams"}), servers=frozenset({"radar"}))
MAX_BODY = 256_000
WELCOME = ("Hello, I am Radar. Ask me about City Holdings projects, for example \"What is off track?\" or "
           "\"How is LOYAL02?\". I answer here and in the Portfolio Radar app. To approve drafts, use the app.")


class TeamsBot:
    def __init__(self, gateway: Gateway, *, verifier_factory=BotTokenVerifier, connector_factory=BotConnector) -> None:
        self.gateway = gateway
        self._verifier_factory = verifier_factory
        self._connector_factory = connector_factory
        self._verifier: BotTokenVerifier | None = None
        self._connector: BotConnector | None = None
        self._key: tuple[str, str, str] | None = None

    async def _setup(self) -> tuple[BotTokenVerifier, BotConnector, str] | None:
        settings = self.gateway.settings
        async with session_scope() as session:
            teams, _ = await integrations.load(session, "teams", settings)
            sso, _ = await integrations.load(session, "sso", settings)
        if not teams.bot_ready() or not sso.tenant_id:
            return None
        store = self.gateway.services.get("secrets")
        try:
            password = await resolve(store, teams.bot_password_ref) if store else ""
        except SecretError:
            password = ""
        if not password:
            return None
        key = (teams.bot_app_id, password, sso.tenant_id)
        if key != self._key:
            self._verifier = self._verifier_factory(teams.bot_app_id)
            self._connector = self._connector_factory(teams.bot_app_id, password, sso.tenant_id)
            self._key = key
        return self._verifier, self._connector, sso.tenant_id

    async def handle(self, request: Request) -> Response:
        if int(request.headers.get("content-length") or 0) > MAX_BODY:
            return JSONResponse({"error": "too large"}, status_code=413)
        setup = await self._setup()
        if setup is None:
            return JSONResponse({"error": "Teams chat is not set up (Admin → Connections → Teams)"}, status_code=503)
        verifier, connector, tenant = setup
        try:
            activity: dict[str, Any] = await request.json()
            service_url = safe_service_url(activity.get("serviceUrl", ""))
            verifier.verify(request.headers.get("authorization"), service_url)
        except BotAuthError as e:
            log.warning("Teams message refused: %s", e)
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        except ValueError:
            return JSONResponse({"error": "bad request"}, status_code=400)

        conv = activity.get("conversation") or {}
        channel = activity.get("channelData") or {}
        if (channel.get("tenant") or {}).get("id") != tenant or conv.get("tenantId", tenant) != tenant:
            log.warning("Teams message from another tenant refused")
            return Response(status_code=403)
        kind = activity.get("type")
        if kind == "conversationUpdate":
            added = [m.get("id") for m in activity.get("membersAdded") or []]
            bot_id = (activity.get("recipient") or {}).get("id")
            if conv.get("conversationType") == "personal" and bot_id in added:
                await self._say(connector, service_url, conv.get("id", ""), WELCOME)
            return Response(status_code=200)
        if kind != "message":
            return Response(status_code=200)
        if conv.get("conversationType") != "personal":
            await self._say(connector, service_url, conv.get("id", ""),
                            "I only answer in a 1:1 chat. Message me directly.", activity.get("id"))
            return Response(status_code=200)
        text = (activity.get("text") or "").strip()
        if not text:
            return Response(status_code=200)

        sender = activity.get("from") or {}
        try:
            member = await connector.member(service_url, conv["id"], sender.get("id", ""))
        except BotAuthError as e:
            log.warning("Teams member lookup failed: %s", e)
            member = None
        upn = (member or {}).get("userPrincipalName") or (member or {}).get("email")
        if not upn or (member or {}).get("aadObjectId", sender.get("aadObjectId")) != sender.get("aadObjectId"):
            await self._say(connector, service_url, conv["id"], "I could not find your City account. Please use the app.",
                            activity.get("id"))
            return Response(status_code=200)

        r = await self.gateway.call(TEAMS, "radar", "ask_from_teams", {
            "user": upn, "text": text[:2000], "service_url": service_url, "conversation_id": conv["id"],
            "activity_id": activity.get("id", "")})
        if r.outcome != "ok":
            log.warning("ask_from_teams %s: %s", r.outcome, r.message)
            await self._say(connector, service_url, conv["id"], "Sorry, I cannot take questions just now. Please use the app.",
                            activity.get("id"))
        return Response(status_code=200)

    async def _say(self, connector: BotConnector, service_url: str, conversation_id: str, text: str,
                   reply_to: str | None = None) -> None:
        """Fixed replies from the bot itself (welcome, wrong chat). Radar's answers go through the notifier."""
        try:
            await connector.send(service_url, conversation_id, text, reply_to)
        except Exception as e:  # noqa: BLE001  a failed courtesy reply must not fail the request
            log.warning("Teams reply failed: %s", type(e).__name__)
