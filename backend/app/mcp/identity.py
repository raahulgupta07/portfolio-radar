"""Who is calling. Every call resolves to a Caller before any tool runs.

Three kinds of caller, as in Uber's MCP Gateway:
- human:   a person, through the web app, with their City SSO token
- agent:   Radar, CityGPT, Claude or another City agent
- service: the adapter or the Notifier
"""

from dataclasses import dataclass, field
from typing import Literal

from app.settings import Settings

CallerKind = Literal["human", "agent", "service"]
CALLER_KINDS: tuple[CallerKind, ...] = ("human", "agent", "service")


@dataclass(frozen=True)
class Caller:
    kind: CallerKind
    id: str
    roles: frozenset[str] = field(default_factory=frozenset)

    def has_any_role(self, roles: frozenset[str]) -> bool:
        return not roles or bool(self.roles & roles)



class UnknownToken(Exception):
    pass


class EntraVerifier:
    """Checks Microsoft Entra ID access tokens (City SSO): signature from the
    tenant's published keys, issuer, audience and expiry. Roles come from the
    user's Entra groups (ENTRA_GROUP_ROLES); apps signing in as themselves must
    be listed in ENTRA_APPS."""

    def __init__(self, settings: Settings, jwks_client=None) -> None:
        import jwt

        self._jwt = jwt
        self.settings = settings
        tenant = settings.entra_tenant_id
        self.issuers = {f"https://login.microsoftonline.com/{tenant}/v2.0", f"https://sts.windows.net/{tenant}/"}
        self.jwks = jwks_client or jwt.PyJWKClient(
            f"https://login.microsoftonline.com/{tenant}/discovery/v2.0/keys", cache_keys=True, lifespan=3600)

    def resolve(self, token: str) -> Caller:
        jwt = self._jwt
        try:
            key = self.jwks.get_signing_key_from_jwt(token).key
            claims = jwt.decode(token, key, algorithms=["RS256"], audience=self.settings.entra_audience,
                                options={"require": ["exp", "iss", "aud"]})
        except jwt.PyJWTError as e:
            raise UnknownToken(f"Token rejected: {type(e).__name__}") from e
        if claims.get("iss") not in self.issuers:
            raise UnknownToken("Token rejected: wrong issuer")

        if claims.get("idtyp") == "app" or ("scp" not in claims and "oid" in claims and "upn" not in claims
                                            and "preferred_username" not in claims):
            app_id = claims.get("azp") or claims.get("appid") or ""
            spec = self.settings.entra_apps.get(app_id)
            if not spec or spec.get("kind") not in ("agent", "service"):
                raise UnknownToken("This app is not allowed to use the gateway")
            return Caller(kind=spec["kind"], id=str(spec.get("id", app_id)), roles=frozenset(spec.get("roles", [])))

        roles = set(self.settings.entra_default_roles)
        for group in claims.get("groups", []) or []:
            roles.update(self.settings.entra_group_roles.get(group, []))
        user_id = claims.get("preferred_username") or claims.get("upn") or claims.get("oid")
        return Caller(kind="human", id=str(user_id), roles=frozenset(roles))


class TokenResolver:
    """Turns a bearer token into a Caller.

    Dev and test: tokens from the DEV_TOKENS setting. Production: City SSO
    (Entra ID) access tokens. Without a valid token the caller is rejected;
    there is no anonymous access.
    """

    def __init__(self, settings: Settings, entra: "EntraVerifier | None" = None) -> None:
        self._entra = entra or (EntraVerifier(settings) if settings.entra_tenant_id else None)
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
        if self._entra is not None and token.count(".") == 2:
            return self._entra.resolve(token)
        raise UnknownToken("Unknown or expired token")
