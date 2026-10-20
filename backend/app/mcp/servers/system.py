"""`/system/mcp`: checks any caller can use to test their connection."""

from datetime import UTC, datetime, timedelta

from pydantic import BaseModel, Field

from app.db import session_scope
from app.mcp.registry import ServerDef, ToolContext
from app.models.mcp import McpPerson

server = ServerDef(
    name="system",
    title="System",
    description="Connection checks for any caller.",
    owner="Portfolio owner (IT)",
    direction="out",
)


class WhoAmI(BaseModel):
    name: str | None = Field(None, max_length=200, description="Your display name, kept for Admin → People")


@server.tool(callers={"human", "agent", "service"}, input_model=WhoAmI, read_only=False, redact=False)
async def whoami(args: WhoAmI, ctx: ToolContext) -> dict:
    """Show who the gateway thinks you are: caller kind, id and roles. For people it also records the
    sign-in, so admins see them in Admin → People."""
    c = ctx.caller
    if c.kind == "human":
        await _seen(ctx, args.name)
    return {"kind": c.kind, "id": c.id, "roles": sorted(c.roles)}


async def _seen(ctx: ToolContext, name: str | None) -> None:
    pid = ctx.caller.id.lower()
    directory = ctx.services.get("directory")
    rule = directory.people.get(pid) if directory else None
    sso_roles = sorted(ctx.caller.roles - (rule.extra_roles if rule else frozenset()))
    now = datetime.now(UTC)
    async with session_scope() as session:
        p = await session.get(McpPerson, pid)
        if p is None:
            session.add(McpPerson(id=pid, name=(name or "")[:200], sso_roles=sso_roles, first_seen=now, last_seen=now))
        elif (p.last_seen is None or now - p.last_seen > timedelta(minutes=1) or p.sso_roles != sso_roles
              or (name and name[:200] != p.name)):
            p.last_seen, p.sso_roles = now, sso_roles
            if p.first_seen is None:
                p.first_seen = now
            if name:
                p.name = name[:200]


@server.tool(callers={"human", "agent", "service"})
async def ping(args, ctx: ToolContext) -> dict:
    """Check the gateway is up. Returns the server time in UTC."""
    return {"ok": True, "time": datetime.now(UTC).isoformat()}
