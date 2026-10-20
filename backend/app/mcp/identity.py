"""Who is calling. Every call resolves to a Caller before any tool runs.

Three kinds of caller, as in Uber's MCP Gateway:
- human:   a person, through the web app, with their City SSO token
- agent:   Radar, CityGPT, Claude or another City agent
- service: the adapter or the Notifier
"""

import time
from dataclasses import dataclass, field, replace
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
    user_apps: tuple[str, ...] = ()  # client IDs people sign in through, besides ENTRA_USER_APPS
    provider: str = "entra"  # entra or keycloak
    issuer: str = ""  # Keycloak realm address (what tokens say in "iss")
    internal_url: str = ""  # where the gateway fetches the realm's keys, if not at the issuer

    @property
    def configured(self) -> bool:
        return bool((self.issuer if self.provider == "keycloak" else self.tenant_id) and self.audience)


@dataclass(frozen=True)
class PersonRule:
    """Set in Admin → People: roles on top of what SSO groups give, or blocked."""
    extra_roles: frozenset[str] = frozenset()
    blocked: bool = False


class Directory:
    """Agents and SSO rules saved in Admin, kept in memory so token checks need
    no database call. The gateway refreshes it at start-up, after every change
    in Admin, and every IDENTITY_REFRESH_SECONDS (for other copies)."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.agents: dict[str, Caller] = {}  # app (client) ID -> caller
        self.sso = SsoRules(settings.entra_tenant_id, settings.entra_audience, tuple(settings.entra_default_roles),
                            {g: tuple(r) for g, r in settings.entra_group_roles.items()},
                            provider=settings.sso_provider, issuer=settings.oidc_issuer,
                            internal_url=settings.oidc_internal_issuer)
        self.people: dict[str, PersonRule] = {}  # person id (lower case) -> rule
        self.loaded_at = 0.0

    def set(self, agents: dict[str, Caller], sso: SsoRules, people: dict[str, PersonRule] | None = None) -> None:
        self.agents, self.sso, self.loaded_at = agents, sso, time.monotonic()
        if people is not None:
            self.people = people

    def apply_person(self, caller: Caller) -> Caller:
        """Blocked people are refused; extra roles from Admin → People are added."""
        rule = self.people.get(caller.id.lower())
        if rule is None:
            return caller
        if rule.blocked:
            raise UnknownToken("This account is blocked in Admin → People")
        return replace(caller, roles=caller.roles | rule.extra_roles) if rule.extra_roles else caller

    def app(self, app_id: str) -> Caller | None:
        spec: dict[str, Any] | None = self.settings.entra_apps.get(app_id)
        if spec and spec.get("kind") in ("agent", "service"):
            return Caller(kind=spec["kind"], id=str(spec.get("id", app_id)), roles=frozenset(spec.get("roles", [])))
        return self.agents.get(app_id)



class UnknownToken(Exception):
    pass


class SsoVerifier:
    """Checks City SSO access tokens: Microsoft Entra ID or a Keycloak realm. Signature from the provider's
    published keys, issuer, audience and expiry. Roles come from the person's groups (Entra group IDs, or
    Keycloak group names and realm roles, which Keycloak can take from LDAP); apps signing in as themselves
    must be listed in ENTRA_APPS or Admin → Agents."""

    def __init__(self, settings: Settings, jwks_client=None, directory: Directory | None = None) -> None:
        import jwt

        self._jwt = jwt
        self.settings = settings
        self.directory = directory or Directory(settings)
        self.sso = self.directory.sso
        if self.sso.provider == "keycloak":
            issuer = self.sso.issuer.rstrip("/")
            if issuer.startswith("http://") and settings.app_env == "prod":
                raise UnknownToken("Keycloak must be reached over https in production")
            self.issuers = {issuer}
            keys_url = f"{(self.sso.internal_url or issuer).rstrip('/')}/protocol/openid-connect/certs"
        else:
            tenant = self.sso.tenant_id
            self.issuers = {f"https://login.microsoftonline.com/{tenant}/v2.0", f"https://sts.windows.net/{tenant}/"}
            keys_url = f"https://login.microsoftonline.com/{tenant}/discovery/v2.0/keys"
        self.jwks = jwks_client or jwt.PyJWKClient(keys_url, cache_keys=True, lifespan=3600)

    def _is_app(self, claims: dict[str, Any]) -> bool:
        if self.sso.provider == "keycloak":
            # Client-credentials tokens belong to the client's service account.
            return str(claims.get("preferred_username", "")).startswith("service-account-")
        return claims.get("idtyp") == "app" or ("scp" not in claims and "oid" in claims and "upn" not in claims
                                                and "preferred_username" not in claims)

    def _groups(self, claims: dict[str, Any]) -> list[str]:
        groups = list(claims.get("groups", []) or [])
        if self.sso.provider == "keycloak":
            groups += list((claims.get("realm_access") or {}).get("roles", []) or [])
            # Group paths ("/portfolio-pmo") also match by name ("portfolio-pmo").
            groups += [g.rsplit("/", 1)[-1] for g in groups if isinstance(g, str) and "/" in g]
        return [g for g in groups if isinstance(g, str)]

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
        entra = self.sso.provider != "keycloak"
        if entra and claims.get("tid", self.sso.tenant_id) != self.sso.tenant_id:
            raise UnknownToken("Token rejected: another tenant")

        if self._is_app(claims):
            app_id = claims.get("azp") or claims.get("appid") or claims.get("client_id") or ""
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
        for group in self._groups(claims):
            group_roles.update(self.sso.group_roles.get(group, ()))
        guest = entra and str(claims.get("acct", "0")) == "1"
        # Guests (B2B) get only what a group gives them, never the default viewer role.
        roles = group_roles if guest else set(self.sso.default_roles) | group_roles
        if entra:
            user_id = claims.get("preferred_username") or claims.get("upn") or claims.get("oid")
        else:
            user_id = claims.get("email") or claims.get("preferred_username") or claims.get("sub")
        caller = Caller(kind="human", id=str(user_id), roles=frozenset(roles))
        if not roles and str(user_id).lower() not in self.directory.people:
            raise UnknownToken("Token rejected: no access for this account")
        return caller


EntraVerifier = SsoVerifier  # the name used before Keycloak support


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
        if caller is None:
            verifier = self._verifier()
            if verifier is None or token.count(".") != 2:
                raise UnknownToken("Unknown or expired token")
            caller = verifier.resolve(token)
        if caller.kind == "human":
            caller = self.directory.apply_person(caller)
            if not caller.roles:
                raise UnknownToken("Token rejected: no access for this account")
        return caller

    def _verifier(self) -> SsoVerifier | None:
        """City SSO checks, rebuilt when an admin changes the provider, tenant, realm or audience."""
        if self._fixed_entra is not None:
            return self._fixed_entra
        sso = self.directory.sso
        if not sso.configured:
            return None
        key = lambda r: (r.provider, r.tenant_id, r.issuer, r.internal_url, r.audience)  # noqa: E731
        if self._entra is None or key(self._entra.sso) != key(sso):
            self._entra = SsoVerifier(self.settings, directory=self.directory)
        self._entra.sso = sso  # group rules apply at once
        return self._entra
