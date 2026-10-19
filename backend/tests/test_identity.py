"""City SSO tokens: signature, audience, issuer, expiry, group roles, app callers."""

import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from app.mcp.identity import Caller, Directory, EntraVerifier, SsoRules, TokenResolver, UnknownToken
from tests.conftest import make_settings

TENANT = "11111111-2222-3333-4444-555555555555"
AUD = "api://portfolio-radar-gateway"
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER = rsa.generate_private_key(public_exponent=65537, key_size=2048)


class FakeJwks:
    def get_signing_key_from_jwt(self, token):
        return type("K", (), {"key": KEY.public_key()})()


def token(key=KEY, **claims):
    base = {"iss": f"https://login.microsoftonline.com/{TENANT}/v2.0", "aud": AUD, "exp": int(time.time()) + 600,
            "preferred_username": "aung@cityholdings.com.mm", "oid": "u-1", "scp": "access", "groups": []}
    base.update(claims)
    return jwt.encode(base, key, algorithm="RS256")


def resolver(**overrides):
    settings = make_settings(entra_tenant_id=TENANT, entra_audience=AUD, dev_tokens={},
                             entra_group_roles={"g-admins": ["admin", "viewer"], "g-pmo": ["approver"]},
                             entra_apps={"app-citygpt": {"kind": "agent", "id": "citygpt", "roles": ["agent"]}},
                             **overrides)
    return TokenResolver(settings, EntraVerifier(settings, jwks_client=FakeJwks()))


def test_employee_gets_viewer_and_group_roles():
    c = resolver().resolve("Bearer " + token(groups=["g-pmo"]))
    assert c.kind == "human" and c.id == "aung@cityholdings.com.mm"
    assert c.roles == {"viewer", "approver"}


@pytest.mark.parametrize("bad", [
    {"aud": "api://something-else"},
    {"iss": "https://login.microsoftonline.com/other-tenant/v2.0"},
    {"exp": int(time.time()) - 10},
])
def test_wrong_audience_issuer_or_expired_is_rejected(bad):
    with pytest.raises(UnknownToken):
        resolver().resolve("Bearer " + token(**bad))


def test_token_signed_by_another_key_is_rejected():
    with pytest.raises(UnknownToken):
        resolver().resolve("Bearer " + token(key=OTHER))


def test_listed_app_is_an_agent_and_unlisted_app_is_rejected():
    app = dict(idtyp="app", azp="app-citygpt", scp=None, preferred_username=None)
    c = resolver().resolve("Bearer " + token(**{k: v for k, v in app.items()}))
    assert (c.kind, c.id, c.roles) == ("agent", "citygpt", {"agent"})
    with pytest.raises(UnknownToken, match="not allowed"):
        resolver().resolve("Bearer " + token(idtyp="app", azp="app-unknown"))


def test_dev_tokens_do_not_work_in_prod():
    settings = make_settings(app_env="prod")
    with pytest.raises(UnknownToken):
        TokenResolver(settings).resolve("Bearer t-viewer")


def test_agents_and_sso_rules_saved_in_admin_apply_without_restart():
    settings = make_settings(dev_tokens={})
    directory = Directory(settings)
    resolver = TokenResolver(settings, directory=directory)
    with pytest.raises(UnknownToken):  # SSO not set up yet
        resolver.resolve("Bearer " + token())

    claude = Caller("agent", "claude-for-pmo", frozenset({"agent"}), frozenset({"portfolio"}), 60)
    directory.set({"app-claude": claude}, SsoRules(TENANT, AUD, ("viewer",), {"g-pmo": ("approver",)}))
    resolver._verifier().jwks = FakeJwks()
    assert resolver.resolve("Bearer " + token(groups=["g-pmo"])).roles == {"viewer", "approver"}
    assert resolver.resolve("Bearer " + token(idtyp="app", azp="app-claude")) == claude

    directory.set({}, directory.sso)  # agent turned off in Admin
    with pytest.raises(UnknownToken, match="not allowed"):
        resolver.resolve("Bearer " + token(idtyp="app", azp="app-claude"))
