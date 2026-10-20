"""Loads agents (Admin → Agents) and City SSO rules (Admin → Connections) into
the in-memory Directory that token checks use."""

from __future__ import annotations

import re

from sqlalchemy import func, select

from app import integrations
from app.db import session_scope
from app.integrations import SsoConfig
from app.mcp.identity import Caller, Directory, PersonRule, SsoRules
from app.models.mcp import McpAgent, McpPerson

# Roles an agent or service set up in Admin may have. Approver and admin are for people only.
AGENT_ROLES = {"agent": ["agent"], "service": ["adapter", "radar", "notifier"]}
# Built-in callers: their tokens come from the environment, not from Admin.
BUILT_IN = [
    {"caller_id": "radar", "name": "Radar chat", "kind": "agent", "servers": ["portfolio", "radar"],
     "what": "Answers people's questions"},
    {"caller_id": "radar-job", "name": "Radar daily check", "kind": "service", "servers": ["portfolio", "radar"],
     "what": "Checks every project after the sync, writes findings and drafts"},
    {"caller_id": "adapter", "name": "Nightly sync", "kind": "service", "servers": ["jira", "openproject", "multica"],
     "what": "Reads the trackers"},
    {"caller_id": "notifier", "name": "Notifier", "kind": "service", "servers": ["notify"],
     "what": "Sends drafts a person approved, and Radar's answers to Teams chats"},
    {"caller_id": "teams", "name": "Teams bot", "kind": "service", "servers": ["radar"],
     "what": "Passes people's 1:1 Teams messages to Radar, after Microsoft's token is checked"},
]


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:64]


def to_caller(a: McpAgent) -> Caller:
    return Caller(kind=a.kind, id=a.caller_id, roles=frozenset(a.roles), servers=frozenset(a.servers),
                  rate_limit=a.rate_limit)


def sso_rules(cfg: SsoConfig) -> SsoRules:
    return SsoRules(cfg.tenant_id, cfg.audience, tuple(cfg.default_roles),
                    {g.group_id: tuple(g.roles) for g in cfg.groups}, tuple(getattr(cfg, "user_apps", ()) or ()),
                    provider=getattr(cfg, "provider", "entra") or "entra", issuer=getattr(cfg, "issuer", "") or "",
                    internal_url=getattr(cfg, "internal_url", "") or "")


async def refresh(directory: Directory) -> None:
    async with session_scope() as session:
        rows = (await session.scalars(select(McpAgent).where(McpAgent.enabled.is_(True)))).all()
        sso, _ = await integrations.load(session, "sso", directory.settings)
        people = (await session.scalars(select(McpPerson).where(
            (McpPerson.blocked.is_(True)) | (func.json_array_length(McpPerson.extra_roles) > 0)))).all()
    directory.set({a.app_id: to_caller(a) for a in rows}, sso_rules(sso),
                  {p.id: PersonRule(frozenset(p.extra_roles), p.blocked) for p in people})
