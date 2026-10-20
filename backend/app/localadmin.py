"""The superadmin: one local account with a password, for setting the app up before City SSO
works, and as a break-glass way in if SSO is down.

- Off unless SUPERADMIN_USERNAME and a password (SUPERADMIN_PASSWORD_HASH, or SUPERADMIN_PASSWORD
  in dev) are set. Make the hash with `python -m app.localadmin hash`.
- Gets the viewer and admin roles, not approver: approvals stay with named people.
- Signs in at the gateway (POST /auth/local), which returns a short-lived token signed with a key
  derived from the password hash, so changing the password ends every superadmin session.
- After 5 wrong tries from one address, or 20 in all, sign-in waits 15 minutes. Every try is in
  the audit log.
"""

from __future__ import annotations

import base64
import getpass
import hashlib
import hmac
import secrets
import sys
import time
from dataclasses import dataclass, field

import jwt

from app.mcp.identity import Caller, UnknownToken
from app.settings import Settings

ISSUER = "portfolio-radar-local"
AUDIENCE = "portfolio-radar-gateway"
ROLES = frozenset({"viewer", "admin"})
MAX_FAILS_PER_CLIENT = 5
MAX_FAILS_TOTAL = 20
LOCK_SECONDS = 15 * 60
N, R, P = 2**14, 8, 1  # scrypt cost


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=N, r=R, p=P, dklen=32)
    # ":" not "$", so the hash can sit in .env files and Docker Compose without escaping.
    return f"scrypt:{N}:{R}:{P}:{_b64(salt)}:{_b64(digest)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        kind, n, r, p, salt, digest = stored.split(":")
        if kind != "scrypt":
            return False
        got = hashlib.scrypt(password.encode(), salt=_unb64(salt), n=int(n), r=int(r), p=int(p), dklen=32)
        return hmac.compare_digest(got, _unb64(digest))
    except (ValueError, TypeError):
        return False


@dataclass
class _Fails:
    by_client: dict[str, list[float]] = field(default_factory=dict)
    all: list[float] = field(default_factory=list)


class LocalAdmin:
    def __init__(self, settings: Settings, clock=time.time) -> None:
        self.settings = settings
        self.clock = clock
        self.username = settings.superadmin_username.strip()
        stored = settings.superadmin_password_hash.strip()
        if not stored and settings.superadmin_password:
            if settings.app_env == "prod":
                raise ValueError("In production set SUPERADMIN_PASSWORD_HASH (python -m app.localadmin hash), "
                                 "not SUPERADMIN_PASSWORD")
            stored = hash_password(settings.superadmin_password)
        self.stored = stored
        # Tokens are signed with a key from the stored hash: a new password ends every session.
        self._key = hashlib.sha256(b"portfolio-radar-local-admin|" + stored.encode()).digest() if stored else b""
        self._fails = _Fails()

    @property
    def enabled(self) -> bool:
        return bool(self.username and self.stored)

    @property
    def caller_id(self) -> str:
        return f"local:{self.username}"

    def _recent(self, times: list[float]) -> list[float]:
        now = self.clock()
        return [t for t in times if now - t < LOCK_SECONDS]

    def locked(self, client: str) -> bool:
        self._fails.all = self._recent(self._fails.all)
        mine = self._fails.by_client[client] = self._recent(self._fails.by_client.get(client, []))
        return len(mine) >= MAX_FAILS_PER_CLIENT or len(self._fails.all) >= MAX_FAILS_TOTAL

    def sign_in(self, username: str, password: str, client: str) -> str | None:
        """A token, or None (wrong name or password, or locked). Always does the slow hash check."""
        if not self.enabled or self.locked(client):
            return None
        good_password = verify_password(password, self.stored)
        if not (hmac.compare_digest(username.strip().lower(), self.username.lower()) and good_password):
            now = self.clock()
            self._fails.by_client.setdefault(client, []).append(now)
            self._fails.all.append(now)
            return None
        self._fails.by_client.pop(client, None)
        now = int(self.clock())
        claims = {"iss": ISSUER, "aud": AUDIENCE, "sub": self.username, "iat": now,
                  "exp": now + 60 * self.settings.superadmin_session_minutes, "jti": secrets.token_hex(8)}
        return jwt.encode(claims, self._key, algorithm="HS256")

    def resolve(self, token: str) -> Caller | None:
        """The superadmin for one of our own tokens; None if the token is not ours."""
        if not self.enabled:
            return None
        try:
            if jwt.decode(token, options={"verify_signature": False}).get("iss") != ISSUER:
                return None
        except jwt.PyJWTError:
            return None
        try:
            claims = jwt.decode(token, self._key, algorithms=["HS256"], audience=AUDIENCE, issuer=ISSUER,
                                options={"require": ["exp", "iss", "aud", "sub"]})
        except jwt.PyJWTError as e:
            raise UnknownToken(f"Superadmin token rejected: {type(e).__name__}") from e
        if claims["sub"] != self.username:
            raise UnknownToken("Superadmin token rejected")
        return Caller(kind="human", id=self.caller_id, roles=ROLES)


def main() -> None:
    if sys.argv[1:] != ["hash"]:
        raise SystemExit("Usage: python -m app.localadmin hash   (asks for the password, prints the hash)")
    pw = getpass.getpass("Superadmin password (12+ characters): ")
    if len(pw) < 12:
        raise SystemExit("Use at least 12 characters")
    if getpass.getpass("Again: ") != pw:
        raise SystemExit("The two passwords differ")
    print(hash_password(pw))


if __name__ == "__main__":
    main()
