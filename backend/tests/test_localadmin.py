"""The superadmin: local name and password, short tokens, lock-out, audit."""

import httpx
import pytest
from sqlalchemy import select

from app.db import session_scope
from app.localadmin import LocalAdmin, hash_password, verify_password
from app.main import create_app
from app.mcp.identity import TokenResolver, UnknownToken
from app.models.mcp import McpCall
from tests.conftest import make_settings


def test_hash_round_trip_and_no_dollar_signs():
    h = hash_password("correct horse battery")
    assert h.startswith("scrypt:") and "$" not in h
    assert verify_password("correct horse battery", h) and not verify_password("wrong", h)


def test_sign_in_gives_a_viewer_admin_token_that_the_resolver_accepts():
    s = make_settings(superadmin_username="root", superadmin_password_hash=hash_password("long password 1"))
    la = LocalAdmin(s)
    token = la.sign_in("ROOT", "long password 1", "10.0.0.1")
    caller = TokenResolver(s, local_admin=la).resolve(f"Bearer {token}")
    assert (caller.kind, caller.id, caller.roles) == ("human", "local:root", {"viewer", "admin"})  # never approver
    # A new password ends every session.
    la2 = LocalAdmin(make_settings(superadmin_username="root", superadmin_password_hash=hash_password("another one 22")))
    with pytest.raises(UnknownToken):
        TokenResolver(s, local_admin=la2).resolve(f"Bearer {token}")


def test_wrong_passwords_lock_the_sign_in():
    now = [1000.0]
    la = LocalAdmin(make_settings(superadmin_username="root", superadmin_password="dev password 1"), clock=lambda: now[0])
    for _ in range(5):
        assert la.sign_in("root", "nope", "1.2.3.4") is None
    assert la.sign_in("root", "dev password 1", "1.2.3.4") is None  # locked, even with the right password
    assert la.sign_in("root", "dev password 1", "5.6.7.8")  # another address still works
    now[0] += 15 * 60 + 1
    assert la.sign_in("root", "dev password 1", "1.2.3.4")


def test_off_unless_set_and_prod_needs_a_hash():
    assert not LocalAdmin(make_settings()).enabled
    with pytest.raises(ValueError, match="HASH"):
        LocalAdmin(make_settings(app_env="prod", superadmin_username="root", superadmin_password="plain text 123"))


async def test_gateway_endpoint_signs_in_and_audits(engine):
    s = make_settings(superadmin_username="root", superadmin_password="dev password 1")
    app = create_app(s, services={"connectors": {}, "secrets": None})
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1") as c:
        assert (await c.get("/auth/local")).json() == {"enabled": True}
        bad = await c.post("/auth/local", json={"username": "root", "password": "x"})
        assert bad.status_code == 401
        good = await c.post("/auth/local", json={"username": "root", "password": "dev password 1"})
        assert good.status_code == 200 and good.json()["id"] == "local:root"
    async with session_scope() as session:
        rows = (await session.scalars(select(McpCall).where(McpCall.tool == "local_sign_in"))).all()
    assert [r.outcome for r in rows] == ["denied", "ok"]
    assert all("dev password" not in (r.args or "") for r in rows)
