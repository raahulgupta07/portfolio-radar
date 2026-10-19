"""`/system/mcp`: checks any caller can use to test their connection."""

from datetime import UTC, datetime

from app.mcp.registry import ServerDef, ToolContext

server = ServerDef(
    name="system",
    title="System",
    description="Connection checks for any caller.",
    owner="Portfolio owner (IT)",
    direction="out",
)


@server.tool(callers={"human", "agent", "service"}, redact=False)
async def whoami(args, ctx: ToolContext) -> dict:
    """Show who the gateway thinks you are: caller kind, id and roles."""
    return {"kind": ctx.caller.kind, "id": ctx.caller.id, "roles": sorted(ctx.caller.roles)}


@server.tool(callers={"human", "agent", "service"})
async def ping(args, ctx: ToolContext) -> dict:
    """Check the gateway is up. Returns the server time in UTC."""
    return {"ok": True, "time": datetime.now(UTC).isoformat()}
