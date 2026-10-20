"""`/admin/mcp`, part 3: Admin → People. Who signed in, with roles from their SSO groups; admins can add
roles, add someone ahead of their first sign-in, or block a person. Human admins only.

Roles normally come from SSO groups (Entra ID, or Keycloak, which can take them from LDAP). Rules here
apply on top, on the next call, without anyone signing in again.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import or_, select

from app.db import session_scope
from app.mcp import agents as agent_dir
from app.mcp.guard import ToolError
from app.mcp.registry import ToolContext
from app.mcp.servers.admin import CALLERS, ROLES, server
from app.models.mcp import McpPerson

Role = Literal["viewer", "approver", "admin"]


def _row(p: McpPerson) -> dict:
    return {"id": p.id, "name": p.name, "sso_roles": p.sso_roles, "extra_roles": p.extra_roles,
            "roles": sorted(set(p.sso_roles) | set(p.extra_roles)), "blocked": p.blocked, "note": p.note,
            "first_seen": p.first_seen.isoformat() if p.first_seen else None,
            "last_seen": p.last_seen.isoformat() if p.last_seen else None, "updated_by": p.updated_by}


class PeopleQuery(BaseModel):
    q: str = Field("", max_length=100, description="Part of a name or account")
    limit: int = Field(200, ge=1, le=1000)


@server.tool(callers=CALLERS, roles=ROLES, input_model=PeopleQuery, redact=False)
async def list_people(args: PeopleQuery, ctx: ToolContext) -> dict:
    """Everyone who signed in or was added by an admin: roles from SSO groups, roles added here, blocked or not,
    first and last sign-in. Newest sign-in first."""
    async with session_scope() as session:
        q = select(McpPerson)
        if args.q.strip():
            like = f"%{args.q.strip().lower()}%"
            q = q.where(or_(McpPerson.id.ilike(like), McpPerson.name.ilike(like)))
        rows = (await session.scalars(q.order_by(McpPerson.last_seen.desc().nulls_last(), McpPerson.id)
                                      .limit(args.limit))).all()
    return {"count": len(rows), "people": [_row(p) for p in rows]}


class PersonArgs(BaseModel):
    id: str = Field(min_length=3, max_length=200, pattern=r"^[^\s]+$",
                    description="The person's account as SSO gives it (email or user principal name)")
    name: str | None = Field(None, max_length=200)
    extra_roles: list[Role] = Field(default_factory=list, description="Roles on top of what their SSO groups give")
    blocked: bool = False
    note: str = Field("", max_length=300, description="Why, for other admins")


@server.tool(callers=CALLERS, roles=ROLES, input_model=PersonArgs, read_only=False)
async def save_person(args: PersonArgs, ctx: ToolContext) -> dict:
    """Add roles to a person, add someone before their first sign-in, or block a person. Applies on their next
    call. You cannot block yourself."""
    pid = args.id.strip().lower()
    if pid == ctx.caller.id.lower() and args.blocked:
        raise ToolError("You cannot block yourself")
    async with session_scope() as session:
        p = await session.get(McpPerson, pid)
        if p is None:
            p = McpPerson(id=pid, name=args.name or "", sso_roles=[])
            session.add(p)
        if args.name is not None:
            p.name = args.name
        p.extra_roles, p.blocked, p.note, p.updated_by = sorted(set(args.extra_roles)), args.blocked, args.note, ctx.caller.id
        await session.flush()
        out = _row(p)
    if "directory" in ctx.services:
        await agent_dir.refresh(ctx.services["directory"])
    return out
