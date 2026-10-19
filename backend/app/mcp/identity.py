"""Who is calling. Every call resolves to a Caller before any tool runs.

Three kinds of caller, as in Uber's MCP Gateway:
- human:   a person, through the web app, with their City SSO token
- agent:   Radar, CityGPT, Claude or another City agent
- service: the adapter or the Notifier
"""

import time
from dataclasses import dataclass, field
from typing import Any, Literal

from app.settings import Settings

CallerKind = Literal["human", "agent", "service"]
CALLER_KINDS: tuple[CallerKind, ...] = ("human", "agent", "service")


@dataclass(frozen=True)
class Caller:
    kind: CallerKind
    id: str
    roles: frozenset[str] = field(default_factory=frozenset)
    # Agents set up in Admin → Agents: the only servers they may use (omni and
    # system always), and their own rate limit. None = no extra limit.
    servers: frozenset[str] | None = None
    rate_limit: int | None = None

    def has_any_role(self, roles: frozenset[str]) -> bool:
        return not roles or bool(self.roles & roles)

    def may_use_server(self, server: str) -> bool:
        return self.servers is None or server in self.servers or server in ("omni", "system")


@dataclass(frozen=True)
class SsoRules:
    tenant_id: str
    audience: str
    default_roles: tuple[str, ...]
    group_roles: dict[str, tuple[str, ...]]
    user_apps: tuple[str, ...] = ()  # app registrations people sign in through, besides ENTRA_USER_APPS


class Directory:
    """Agents and SSO rules saved in Admin, kept in memory so token checks need
    no database call. The gateway refreshes it at start-up, after every change
    in Admin, and every IDENTITY_REFRESH_SECONDS (for other copies)."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.agents: dict[str, Caller] = {}  # Entra app ID -> caller
        self.sso = SsoRules(settings.entra_tenant_id, settings.entra_audience, tuple(settings.entra_default_roles),
                            {g: tuple(r) for g, r in settings.entra_group_roles.items()})
        self.loaded_at = 0.0

    def set(self, agents: dict[str, Caller], sso: SsoRules) -> None:
        self.agents, self.sso, self.loaded_at = agents, sso, time.monotonic()

    def app(self, app_id: str) -> Caller | None:
        spec: dict[str, Any] | None = self.settings.entra_apps.get(app_id)
        if spec and spec.get("kind") in ("agent", "service"):
            return Caller(kind=spec["kind"], id=str(spec.get("id", app_id)), roles=frozenset(spec.get("roles", [])))
        return self.agents.get(app_id)



class UnknownToken(Exception):
    pass


class EntraVerifier:
    """Checks Microsoft Entra ID access tokens (City SSO): signature from the
    tenant's published keys, issuer, audience and expiry. Roles come from the
    user's Entra groups (ENTRA_GROUP_ROLES); apps signing in as themselves must
    be listed in ENTRA_APPS."""

    def __init__(self, settings: Settings, jwks_client=None, directory: Directory | None = None) -> None:
        import jwt

        self._jwt = jwt
        self.settings = settings
        self.directory = directory or Directory(settings)
        self.sso = self.directory.sso
        tenant = self.sso.tenant_id
        self.issuers = {f"https://login.microsoftonline.com/{tenant}/v2.0", f"https://sts.windows.net/{tenant}/"}
        self.jwks = jwks_client or jwt.PyJWKClient(
            f"https://login.microsoftonline.com/{tenant}/discovery/v2.0/keys", cache_keys=True, lifespan=3600)

    def resolve(self, token: str) -> Caller:
        jwt = self._jwt
        try:
            key = self.jwks.get_signing_key_from_jwt(token).key
            claims = jwt.decode(token, key, algorithms=["RS256"], audience=self.sso.audience,
                                options={"require": ["exp", "iss", "aud"]})
        except jwt.PyJWTError as e:
            raise UnknownToken(f"Token rejected: {type(e).__name__}") from e
        if claims.get("iss") not in self.issuers:
            raise UnknownToken("Token rejected: wrong issuer")
        if claims.get("tid", self.sso.tenant_id) != self.sso.tenant_id:
            raise UnknownToken("Token rejected: another tenant")

        if claims.get("idtyp") == "app" or ("scp" not in claims and "oid" in claims and "upn" not in claims
                                            and "preferred_username" not in claims):
            app_id = claims.get("azp") or claims.get("appid") or ""
            caller = self.directory.app(app_id)
            if caller is None:
                raise UnknownToken("This app is not allowed to use the gateway")
            return caller

        # A person's token counts only when it was issued to an app people sign in through (the web app).
        # Otherwise any agent with on-behalf-of rights could act as an approver.
        client = claims.get("azp") or claims.get("appid") or ""
        user_apps = set(self.sso.user_apps) | set(self.settings.entra_user_apps)
        if user_apps and client not in user_apps:
            raise UnknownToken("Token rejected: people sign in through the Portfolio Radar app only")
        if not user_apps and self.settings.app_env == "prod":
            raise UnknownToken("Token rejected: no sign-in app is listed (ENTRA_USER_APPS)")
        group_roles: set[str] = set()
        for group in claims.get("groups", []) or []:
            group_roles.update(self.sso.group_roles.get(group, ()))
        guest = str(claims.get("acct", "0")) == "1"
        # Guests (B2B) get only what a group gives them, never the default viewer role.
        roles = group_roles if guest else set(self.sso.default_roles) | group_roles
        if not roles:
            raise UnknownToken("Token rejected: no access for this account")
        user_id = claims.get("preferred_username") or claims.get("upn") or claims.get("oid")
        return Caller(kind="human", id=str(user_id), roles=frozenset(roles))


class TokenResolver:
    """Turns a bearer token into a Caller.

    Dev and test: tokens from the DEV_TOKENS setting. Production: City SSO
    (Entra ID) access tokens. Without a valid token the caller is rejected;
    there is no anonymous access.
    """

    def __init__(self, settings: Settings, entra: "EntraVerifier | None" = None,
                 directory: Directory | None = None) -> None:
        self.settings = settings
        self.directory = directory or Directory(settings)
        self._fixed_entra = entra
        self._entra: EntraVerifier | None = None
        self._dev_tokens: dict[str, Caller] = {}
        if settings.app_env in ("dev", "test"):
            for token, spec in settings.dev_tokens.items():
                kind = spec.get("kind")
                if kind not in CALLER_KINDS:
                    raise ValueError(f"DEV_TOKENS: bad caller kind {kind!r} for token ending …{token[-4:]}")
                self._dev_tokens[token] = Caller(kind=kind, id=str(spec["id"]), roles=frozenset(spec.get("roles", [])))

    def resolve(self, authorization: str | None) -> Caller:
        if not authorization or not authorization.lower().startswith("bearer "):
            raise UnknownToken("Missing bearer token")
        token = authorization[7:].strip()
        caller = self._dev_tokens.get(token)
        if caller is not None:
            return caller
        entra = self._verifier()
        if entra is not None and token.count(".") == 2:
            return entra.resolve(token)
        raise UnknownToken("Unknown or expired token")

    def _verifier(self) -> EntraVerifier | None:
        """City SSO checks, rebuilt when an admin changes the tenant or audience."""
        if self._fixed_entra is not None:
            return self._fixed_entra
        sso = self.directory.sso
        if not sso.tenant_id or not sso.audience:
            return None
        if self._entra is None or self._entra.sso.tenant_id != sso.tenant_id or self._entra.sso.audience != sso.audience:
            self._entra = EntraVerifier(self.settings, directory=self.directory)
        self._entra.sso = sso  # group rules apply at once
        return self._entra
