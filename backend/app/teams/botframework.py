"""Microsoft Teams through the Bot Framework: check that a message really comes
from Microsoft, look up who sent it, and send Radar's reply.

Incoming: Teams posts each message to our endpoint with a JWT signed by the
Bot Framework (issuer https://api.botframework.com, audience = our bot's app
ID). We check the signature, issuer, audience, expiry and that the token's
`serviceurl` matches the message. Only then is the sender trusted.

Outgoing: replies go to the message's serviceUrl with a token from Entra ID
(client credentials for the bot's app registration). Because that token is
sent to serviceUrl, only Microsoft's Bot Framework hosts are accepted.
"""

from __future__ import annotations

import time
from typing import Any
from urllib.parse import quote, urlparse

import httpx

OPENID_URL = "https://login.botframework.com/v1/.well-known/openidconfiguration"
ISSUER = "https://api.botframework.com"
CONNECTOR_SCOPE = "https://api.botframework.com/.default"
# Where Teams' Bot Connector runs (public cloud). Our token is only ever sent to these.
SERVICE_HOST = "smba.trafficmanager.net"
SERVICE_DOMAIN = ".botframework.com"


class BotAuthError(Exception):
    pass


def safe_service_url(url: str) -> str:
    u = urlparse(url or "")
    host = (u.hostname or "").lower()
    if u.scheme != "https" or u.port not in (None, 443) or not (host == SERVICE_HOST or host.endswith(SERVICE_DOMAIN)):
        raise BotAuthError(f"Service URL not allowed: {host or url!r}")
    return url.rstrip("/") + "/"


class BotTokenVerifier:
    """Checks the Bot Framework's JWT on an incoming message."""

    def __init__(self, app_id: str, jwks_client: Any = None, transport: httpx.BaseTransport | None = None) -> None:
        import jwt

        self._jwt = jwt
        self.app_id = app_id
        self._jwks = jwks_client
        self._transport = transport

    def _keys(self) -> Any:
        if self._jwks is None:
            with httpx.Client(timeout=15, transport=self._transport) as c:
                jwks_uri = c.get(OPENID_URL).raise_for_status().json()["jwks_uri"]
            self._jwks = self._jwt.PyJWKClient(jwks_uri, cache_keys=True, lifespan=3600)
        return self._jwks

    def verify(self, authorization: str | None, service_url: str) -> dict[str, Any]:
        if not authorization or not authorization.lower().startswith("bearer "):
            raise BotAuthError("Missing Bot Framework token")
        token = authorization[7:].strip()
        jwt = self._jwt
        try:
            key = self._keys().get_signing_key_from_jwt(token).key
            claims = jwt.decode(token, key, algorithms=["RS256"], audience=self.app_id, issuer=ISSUER,
                                options={"require": ["exp", "iss", "aud"]}, leeway=300)
        except (jwt.PyJWTError, httpx.HTTPError, KeyError) as e:
            raise BotAuthError(f"Bot Framework token rejected: {type(e).__name__}") from e
        claimed = (claims.get("serviceurl") or claims.get("serviceUrl") or "").rstrip("/")
        if claimed and claimed != service_url.rstrip("/"):
            raise BotAuthError("Service URL does not match the token")
        return claims


class BotConnector:
    """Sends messages and looks up members through the Bot Connector API."""

    def __init__(self, app_id: str, password: str, tenant_id: str, *,
                 transport: httpx.AsyncBaseTransport | None = None, clock=time.monotonic) -> None:
        self.app_id, self.password, self.tenant_id = app_id, password, tenant_id
        self._transport = transport
        self._clock = clock
        self._token: tuple[str, float] | None = None

    async def _bearer(self, c: httpx.AsyncClient) -> str:
        if self._token and self._clock() < self._token[1]:
            return self._token[0]
        r = await c.post(f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token", data={
            "grant_type": "client_credentials", "client_id": self.app_id, "client_secret": self.password,
            "scope": CONNECTOR_SCOPE})
        if r.status_code != 200:
            raise BotAuthError(f"Bot sign-in failed: HTTP {r.status_code}")
        body = r.json()
        self._token = (body["access_token"], self._clock() + int(body.get("expires_in", 3600)) - 300)
        return self._token[0]

    async def _call(self, method: str, url: str, json: dict[str, Any] | None = None) -> httpx.Response:
        async with httpx.AsyncClient(timeout=20, transport=self._transport) as c:
            token = await self._bearer(c)
            return await c.request(method, url, json=json, headers={"Authorization": f"Bearer {token}"})

    async def member(self, service_url: str, conversation_id: str, user_id: str) -> dict[str, Any] | None:
        """The sender's account: userPrincipalName, email, name, aadObjectId."""
        base = safe_service_url(service_url)
        r = await self._call("GET", f"{base}v3/conversations/{quote(conversation_id, safe='')}/members/{quote(user_id, safe='')}")
        return r.json() if r.status_code == 200 else None

    async def send(self, service_url: str, conversation_id: str, text: str, reply_to: str | None = None) -> str:
        base = safe_service_url(service_url)
        activity: dict[str, Any] = {"type": "message", "text": text, "textFormat": "markdown"}
        if reply_to:
            activity["replyToId"] = reply_to
        r = await self._call("POST", f"{base}v3/conversations/{quote(conversation_id, safe='')}/activities", activity)
        if r.status_code >= 300:
            raise BotAuthError(f"Teams did not take the message: HTTP {r.status_code}")
        return (r.json() or {}).get("id", "") if r.content else ""
