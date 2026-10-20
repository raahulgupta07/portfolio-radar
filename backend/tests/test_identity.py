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


async def test_worker_jobs_sign_in_with_their_own_managed_identity():
    from app.servicetokens import ServiceTokens

    class FakeCredential:
        def __init__(self, client_id):
            self.client_id, self.calls = client_id, 0

        async def get_token(self, scope):
            self.calls += 1
            return type("T", (), {"token": f"{self.client_id}|{scope}"})()

    made = []

    def factory(cid):
        made.append(cid)
        return FakeCredential(cid)

    dev = ServiceTokens(make_settings())
    assert await dev.get("adapter") == "dev-adapter"
    s = make_settings(service_auth="managed_identity", gateway_scope="api://city-mcp-gateway/.default",
                      adapter_client_id="id-adapter", notifier_client_id="id-notifier")
    tokens = ServiceTokens(s, credential=factory)
    assert await tokens.get("adapter") == "id-adapter|api://city-mcp-gateway/.default"
    assert await tokens.get("notifier") == "id-notifier|api://city-mcp-gateway/.default"
    await tokens.get("adapter")
    assert made == ["id-adapter", "id-notifier"]  # one credential per identity, reused
    with pytest.raises(RuntimeError, match="radar"):
        await tokens.get("radar")


# -- security review fixes (docs/security-review.md) ---------------------------------

def test_person_tokens_only_from_the_sign_in_app():
    r = resolver(entra_user_apps=["web-app"])
    assert r.resolve("Bearer " + token(azp="web-app")).kind == "human"
    with pytest.raises(UnknownToken, match="Portfolio Radar app only"):
        r.resolve("Bearer " + token(azp="some-agent-obo", groups=["g-pmo"]))  # an agent acting for an approver
    with pytest.raises(UnknownToken, match="ENTRA_USER_APPS"):
        resolver(app_env="prod").resolve("Bearer " + token(azp="web-app"))  # prod must list its sign-in app


def test_other_tenant_and_guests_without_a_group_are_refused():
    with pytest.raises(UnknownToken, match="another tenant"):
        resolver().resolve("Bearer " + token(tid="99999999-2222-3333-4444-555555555555"))
    with pytest.raises(UnknownToken, match="no access"):
        resolver().resolve("Bearer " + token(tid=TENANT, acct=1))
    guest = resolver().resolve("Bearer " + token(tid=TENANT, acct=1, groups=["g-pmo"]))
    assert guest.roles == {"approver"}  # only what the group gives, no default viewer


# -- Keycloak (LDAP behind it) and Admin → People ---------------------------------------

KC = "https://sso.city.local/realms/city"


def kc_token(**claims):
    base = {"iss": KC, "aud": ["portfolio-radar-gateway", "account"], "exp": int(time.time()) + 600,
            "azp": "portfolio-radar-web", "preferred_username": "aye", "email": "aye@city.local",
            "groups": ["/portfolio-viewers"], "realm_access": {"roles": ["offline_access"]}}
    base.update(claims)
    return jwt.encode(base, KEY, algorithm="RS256")


def kc_resolver(people=None, **overrides):
    settings = make_settings(dev_tokens={}, entra_user_apps=["portfolio-radar-web"], **overrides)
    directory = Directory(settings)
    directory.set({}, SsoRules("", "portfolio-radar-gateway", ("viewer",),
                               {"portfolio-pmo": ("approver",), "portfolio-admin": ("admin", "viewer")},
                               provider="keycloak", issuer=KC), people or {})
    return TokenResolver(settings, EntraVerifier(settings, jwks_client=FakeJwks(), directory=directory), directory)


def test_keycloak_person_gets_roles_from_ldap_groups_and_realm_roles():
    c = kc_resolver().resolve("Bearer " + kc_token(groups=["/ldap/portfolio-pmo"]))
    assert (c.kind, c.id, c.roles) == ("human", "aye@city.local", {"viewer", "approver"})
    c = kc_resolver().resolve("Bearer " + kc_token(realm_access={"roles": ["portfolio-admin"]}))
    assert "admin" in c.roles


@pytest.mark.parametrize("bad", [
    {"iss": "https://sso.city.local/realms/other"},
    {"aud": "account"},
    {"azp": "some-other-client"},
])
def test_keycloak_wrong_realm_audience_or_client_is_refused(bad):
    with pytest.raises(UnknownToken):
        kc_resolver().resolve("Bearer " + kc_token(**bad))


def test_keycloak_service_account_must_be_a_listed_agent():
    claude = Caller("agent", "claude", frozenset({"agent"}))
    r = kc_resolver()
    r.directory.agents = {"claude-for-pmo": claude}
    tok = kc_token(preferred_username="service-account-claude-for-pmo", azp="claude-for-pmo", email=None)
    assert r.resolve("Bearer " + tok) == claude
    with pytest.raises(UnknownToken, match="not allowed"):
        r.resolve("Bearer " + kc_token(preferred_username="service-account-x", azp="x"))


def test_people_rules_add_roles_and_block():
    from app.mcp.identity import PersonRule

    r = kc_resolver(people={"aye@city.local": PersonRule(frozenset({"approver"}))})
    assert r.resolve("Bearer " + kc_token()).roles == {"viewer", "approver"}
    r = kc_resolver(people={"aye@city.local": PersonRule(blocked=True)})
    with pytest.raises(UnknownToken, match="blocked"):
        r.resolve("Bearer " + kc_token())
    # Blocks apply to dev tokens too, so they can be tried locally.
    settings = make_settings()
    d = Directory(settings)
    d.people = {"viewer@cityholdings.dev": PersonRule(blocked=True)}
    with pytest.raises(UnknownToken):
        TokenResolver(settings, directory=d).resolve("Bearer t-viewer")


def test_keycloak_over_http_is_refused_in_production():
    settings = make_settings(app_env="prod", dev_tokens={})
    d = Directory(settings)
    d.sso = SsoRules("", "gw", ("viewer",), {}, provider="keycloak", issuer="http://sso.city.local/realms/city")
    with pytest.raises(UnknownToken, match="https"):
        TokenResolver(settings, directory=d).resolve("Bearer a.b.c")
