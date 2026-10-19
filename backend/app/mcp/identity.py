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


ANONYMOUS = Caller(kind="agent", id="anonymous")


class UnknownToken(Exception):
    pass


class TokenResolver:
    """Turns a bearer token into a Caller.

    Dev and test: tokens from the DEV_TOKENS setting. Production: City SSO
    (Entra ID) token check, added in Phase 5. Without a valid token the caller
    is rejected; there is no anonymous access.
    """

    def __init__(self, settings: Settings) -> None:
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
            raise UnknownToken("Unknown or expired token")
        return caller
