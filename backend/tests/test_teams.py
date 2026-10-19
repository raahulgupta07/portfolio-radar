"""Phase 18: two-way chat with Radar in Microsoft Teams.

Teams → gateway /teams/messages (Microsoft's token checked) → radar.ask_from_teams
→ Radar answers (worker) → notifier → the same 1:1 Teams chat. Microsoft's side
(token signing, sign-in, Bot Connector) is played by local fakes.
"""

import json
import time
from datetime import date

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI, Request
from sqlalchemy import select, text

from app.adapter.readers import GatewayReader
from app.adapter.seed import seed
from app.adapter.sync import sync_all
from app.connectors import SOURCES
from app.connectors.mock import MockConnector
from app.db import session_scope
from app.mcp.guard import Gateway
from app.mcp.identity import Directory
from app.mcp.servers import build_registry
from app.models.app import RadarMessage
from app.models.mcp import McpCall
from app.radar.assistant import answer_pending
from app.radar.notifier import deliver_teams_replies
from app.radar.runtime import _channels
from app.secretstore import LocalStore
from app.teams.botframework import BotAuthError, BotConnector, BotTokenVerifier, safe_service_url
from app.teams.endpoint import TeamsBot
from tests.conftest import ADMIN, ADAPTER, BACKEND, NOTIFIER, RADAR, make_settings

SAMPLE = BACKEND.parent / "design" / "sample-data.json"
TENANT = "11111111-2222-3333-4444-555555555555"
BOT_ID = "9a8b7c6d-1111-2222-3333-444455556666"
SERVICE_URL = "https://smba.trafficmanager.net/apac/"
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


class Jwks:
    def get_signing_key_from_jwt(self, token):
        return type("K", (), {"key": KEY.public_key()})()


def bot_token(**over) -> str:
    claims = {"iss": "https://api.botframework.com", "aud": BOT_ID, "exp": int(time.time()) + 600,
              "serviceurl": SERVICE_URL, **over}
    return jwt.encode(claims, KEY, algorithm="RS256")


class Microsoft:
    """Entra sign-in for the bot and the Bot Connector API."""

    def __init__(self) -> None:
        self.sent: list[dict] = []
        self.token_requests = 0

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.url.host == "login.microsoftonline.com":
            self.token_requests += 1
            form = dict(x.split("=", 1) for x in request.content.decode().split("&"))
            if form.get("client_secret") != "bot-secret":
                return httpx.Response(401)
            return httpx.Response(200, json={"access_token": "connector-token", "expires_in": 3600})
        assert request.headers["authorization"] == "Bearer connector-token"
        if "/members/" in request.url.path:
            return httpx.Response(200, json={"id": "29:aye", "aadObjectId": "aad-aye", "name": "Aye Aye",
                                             "userPrincipalName": "aye@cityholdings.dev"})
        if request.url.path.endswith("/activities"):
            self.sent.append({"conversation": request.url.path.split("/")[4], **json.loads(request.content)})
            return httpx.Response(201, json={"id": f"reply-{len(self.sent)}"})
        return httpx.Response(404)


def activity(text_="What is off track?", conversation_type="personal", tenant=TENANT, service_url=SERVICE_URL, **over):
    return {"type": "message", "id": "act-1", "text": text_, "serviceUrl": service_url,
            "from": {"id": "29:aye", "aadObjectId": "aad-aye", "name": "Aye Aye"},
            "recipient": {"id": f"28:{BOT_ID}"},
            "conversation": {"id": "a:1on1-aye", "conversationType": conversation_type, "tenantId": tenant},
            "channelData": {"tenant": {"id": tenant}}, **over}


@pytest.fixture(autouse=True)
async def clean(engine):
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE app.source, app.prefix, app.setting, app.radar_message, mcp.agent "
                                "RESTART IDENTITY CASCADE"))
    yield


@pytest.fixture
async def setup(tmp_path):
    settings = make_settings(today="2026-10-19")
    registry = build_registry(settings)
    async with session_scope() as session:
        await registry.sync(session)
        for server in registry.servers.values():
            for tool in server.tools:
                await registry.set_status(session, server.name, tool, "on", by="tests")
    await seed()
    ms = Microsoft()
    store = LocalStore(tmp_path / "secrets.json")
    gw = Gateway(registry, settings, {"connectors": {sid: MockConnector(sid, SAMPLE) for sid in SOURCES},
                                      "secrets": store, "directory": Directory(settings)})
    await sync_all(GatewayReader(gw, ADAPTER), settings, date(2026, 10, 19))
    for call in (("save_integration", {"name": "sso", "config": {"tenant_id": TENANT, "audience": "api://gw"}}),
                 ("set_secret", {"ref": "kv://teams-bot-password", "value": "bot-secret"}),
                 ("save_integration", {"name": "teams", "config": {"bot_app_id": BOT_ID,
                                                                   "bot_password_ref": "kv://teams-bot-password"}})):
        r = await gw.call(ADMIN, "admin", *call)
        assert r.outcome == "ok", r.message
    bot = TeamsBot(gw, verifier_factory=lambda app_id: BotTokenVerifier(app_id, jwks_client=Jwks()),
                   connector_factory=lambda *a: BotConnector(*a, transport=httpx.MockTransport(ms)))
    app = FastAPI()

    @app.post("/teams/messages")
    async def messages(request: Request):
        return await bot.handle(request)

    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://gateway")
    yield gw, client, ms
    await client.aclose()


async def post(client, body, token=None):
    return await client.post("/teams/messages", json=body, headers={"Authorization": f"Bearer {token or bot_token()}"})


async def messages() -> list[RadarMessage]:
    async with session_scope() as session:
        return list((await session.scalars(select(RadarMessage).order_by(RadarMessage.id))).all())


async def test_question_in_teams_is_answered_in_the_same_chat(setup):
    gw, client, ms = setup
    r = await post(client, activity())
    assert r.status_code == 200
    [q] = await messages()
    assert (q.user_id, q.kind, q.state, q.body) == ("aye@cityholdings.dev", "me", "pending", "What is off track?")
    assert q.payload_json["teams"]["conversation_id"] == "a:1on1-aye"

    # The worker answers (rules only, no LLM), then the notifier delivers it to Teams.
    assert await answer_pending(GatewayReader(gw, RADAR), gw.settings) == 1
    channels = await _channels(GatewayReader(gw, NOTIFIER), gw.settings, gw.services["secrets"])
    assert (channels.teams_bot_app_id, channels.teams_bot_password, channels.entra_tenant_id) == (BOT_ID, "bot-secret", TENANT)
    delivered = await deliver_teams_replies(GatewayReader(gw, NOTIFIER), channels, transport=httpx.MockTransport(ms))
    assert delivered == 1
    [reply] = ms.sent
    assert reply["conversation"] == "a:1on1-aye" and reply["replyToId"] == "act-1"
    assert "POS03" in reply["text"]  # the rule answer names the off-track project
    # Delivered once only; the same answer also shows in the app's chat for this person.
    assert await deliver_teams_replies(GatewayReader(gw, NOTIFIER), channels, transport=httpx.MockTransport(ms)) == 0
    q, a = await messages()
    assert a.reply_to == q.id and a.payload_json["teams_sent_at"]
    async with session_scope() as session:
        audit = (await session.scalars(select(McpCall).where(McpCall.tool == "ask_from_teams"))).one()
    assert (audit.caller_kind, audit.caller_id, audit.outcome) == ("service", "teams", "ok")


@pytest.mark.parametrize("token_over, body_over, status", [
    ({"aud": "someone-else"}, {}, 401),                      # token for another bot
    ({"iss": "https://evil.example"}, {}, 401),              # not signed as the Bot Framework
    ({"serviceurl": "https://smba.trafficmanager.net/emea/"}, {}, 401),  # token for another service URL
    ({}, {"service_url": "https://evil.example/"}, 401),     # our token would leak to that host
    ({}, {"tenant": "99999999-2222-3333-4444-555555555555"}, 403),  # another company's Teams
])
async def test_messages_not_from_city_teams_are_refused(setup, token_over, body_over, status):
    _, client, ms = setup
    service_url = body_over.get("service_url", SERVICE_URL)
    body = activity(tenant=body_over.get("tenant", TENANT), service_url=service_url)
    r = await post(client, body, bot_token(**token_over))
    assert r.status_code == status
    assert await messages() == [] and ms.sent == []


async def test_group_chats_get_a_pointer_not_an_answer(setup):
    _, client, ms = setup
    r = await post(client, activity(conversation_type="groupChat"))
    assert r.status_code == 200 and await messages() == []
    assert "1:1" in ms.sent[0]["text"]


async def test_welcome_on_install_and_missing_token(setup):
    _, client, ms = setup
    r = await post(client, {**activity(), "type": "conversationUpdate", "membersAdded": [{"id": f"28:{BOT_ID}"}]})
    assert r.status_code == 200 and "I am Radar" in ms.sent[0]["text"]
    r = await client.post("/teams/messages", json=activity())
    assert r.status_code == 401


def test_only_bot_framework_hosts_get_our_token():
    assert safe_service_url("https://smba.trafficmanager.net/apac") == "https://smba.trafficmanager.net/apac/"
    assert safe_service_url("https://europe.botframework.com/x").startswith("https://europe.botframework.com")
    for bad in ("http://smba.trafficmanager.net/apac/", "https://smba.trafficmanager.net.evil.com/",
                "https://evilbotframework.com/", "https://smba.trafficmanager.net:8443/"):
        with pytest.raises(BotAuthError):
            safe_service_url(bad)


async def test_teams_bot_can_only_ask(setup):
    gw, _, _ = setup
    from app.teams.endpoint import TEAMS

    r = await gw.call(TEAMS, "portfolio", "get_overview", {})
    assert r.outcome == "denied"
    r = await gw.call(TEAMS, "radar", "answer_ask", {"message_id": 1, "answer": "yes"})
    assert r.outcome == "denied"
