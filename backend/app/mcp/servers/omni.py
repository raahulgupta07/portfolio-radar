"""`/omni/mcp`: one endpoint, four tools, in front of every server (Uber's
Omni MCP pattern). An agent finds what it needs step by step instead of
loading every tool into its context:

    discover_server → discover_tools → get_tool_schema → invoke_tool

It only shows servers and tools the caller may use, and invoke_tool goes
through the same guard as a direct call.
"""

import re

from pydantic import BaseModel, Field

from app.mcp.guard import ToolError
from app.mcp.registry import ServerDef, ToolContext

server = ServerDef(
    name="omni",
    title="Omni",
    description="Find and call any tool you may use, step by step, through one endpoint.",
    owner="Portfolio owner (IT)",
    direction="out",
)

CALLERS = {"human", "agent", "service"}


class Query(BaseModel):
    query: str = Field("", max_length=200, description="What you need, e.g. 'project risks' or 'sync status'")
    limit: int = Field(5, ge=1, le=20)


class ServerName(BaseModel):
    server: str = Field(max_length=64)


class ToolName(ServerName):
    tool: str = Field(max_length=100)


class Invoke(ToolName):
    arguments: dict = Field(default_factory=dict, description="Inputs that match the tool's schema")
    projection: list[str] | None = Field(None, description="Return only these fields, e.g. ['projects[].code']")


def _usable_servers(ctx: ToolContext):
    return [s for name, s in ctx.services["gateway"].registry.servers.items() if name != "omni"]


@server.tool(callers=CALLERS, redact=False, input_model=Query)
async def discover_server(args: Query, ctx: ToolContext) -> dict:
    """Find servers that fit what you need. Returns names, descriptions and how many tools you may use."""
    gw = ctx.services["gateway"]
    words = [w for w in re.findall(r"\w+", args.query.lower()) if len(w) > 2]
    found = []
    for s in _usable_servers(ctx):
        tools = await gw.list_tools(ctx.caller, s.name)
        if not tools:
            continue
        text = " ".join([s.name, s.title, s.description, *[t.name + " " + t.description for t in tools]]).lower()
        score = sum(text.count(w) for w in words)
        if score or not words:
            found.append((score, {"server": s.name, "title": s.title, "description": s.description,
                                  "tools_you_can_use": len(tools)}))
    found.sort(key=lambda x: -x[0])
    return {"query": args.query, "servers": [f for _, f in found[: args.limit]]}


@server.tool(callers=CALLERS, redact=False, input_model=ServerName)
async def discover_tools(args: ServerName, ctx: ToolContext) -> dict:
    """List the tools you may use on one server: name and one-line description."""
    tools = await ctx.services["gateway"].list_tools(ctx.caller, args.server)
    return {"server": args.server, "tools": [{"tool": t.name, "description": t.description} for t in tools]}


@server.tool(callers=CALLERS, redact=False, input_model=ToolName)
async def get_tool_schema(args: ToolName, ctx: ToolContext) -> dict:
    """Get the exact inputs of one tool you may use."""
    tools = await ctx.services["gateway"].list_tools(ctx.caller, args.server)
    spec = next((t for t in tools if t.name == args.tool), None)
    if spec is None:
        raise ToolError(f"No tool {args.server}.{args.tool} that you may use")
    return {"server": args.server, "tool": spec.name, "description": spec.description,
            "input_schema": spec.input_schema(), "read_only": spec.read_only}


@server.tool(callers=CALLERS, redact=False, input_model=Invoke, read_only=False)
async def invoke_tool(args: Invoke, ctx: ToolContext) -> dict:
    """Call a tool through the gateway. The same checks apply as for a direct call."""
    if args.server == "omni":
        raise ToolError("Call omni tools directly")
    arguments = dict(args.arguments)
    if args.projection:
        arguments["fields"] = args.projection
    r = await ctx.services["gateway"].call(ctx.caller, args.server, args.tool, arguments)
    if r.outcome != "ok":
        raise ToolError(r.message)
    return {"server": args.server, "tool": args.tool, "result": r.value}
