"""`/admin/mcp`: what the Admin page does. Human admins only.

These tools change our own settings (prefixes, schedule, Radar rules, alerts,
tool status). None of them can change project data or write to a tracker:
syncing reads the trackers through the source servers, as the adapter.
"""

from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import func, select

from app import appsettings
from app.adapter.readers import GatewayReader, SourceCallError
from app.adapter.sync import sync_all
from app.db import session_scope
from app.health import today_in
from app.mcp.guard import ToolError
from app.mcp.identity import Caller
from app.mcp.registry import ServerDef, ToolContext
from app.models.app import NonCompliant, Prefix, Project, Source, SyncRun
from app.models.mcp import McpCall, McpTool, McpToolChange
from app.portfolio.queries import sync_status

server = ServerDef(
    name="admin",
    title="Admin",
    description="Sources, prefixes, schedule, Radar rules, alerts, sync log and tool status. Admins only.",
    owner="Portfolio owner (IT)",
    direction="out",
)

CALLERS = {"human"}
ROLES = {"admin"}
ADAPTER = Caller("service", "adapter", frozenset({"adapter"}))
SourceId = Literal["jira", "openproject", "multica"]


class SourceArg(BaseModel):
    source: SourceId


class OptionalSource(BaseModel):
    source: SourceId | None = None


class NewPrefix(BaseModel):
    value: str = Field(pattern=r"^[A-Z0-9]+(-[A-Z0-9]+)*-$", max_length=50,
                       description="Upper case, ending with a dash, e.g. CHL-HR-")
    description: str = Field("", max_length=200)


class PrefixActive(BaseModel):
    value: str = Field(max_length=50)
    active: bool


class SettingsChanges(BaseModel):
    changes: dict[str, Any] = Field(description="Only the settings to change, e.g. {\"sync_time\": \"03:00\"}")


class SyncLogArgs(BaseModel):
    limit: int = Field(50, ge=1, le=500)
    source: SourceId | None = None


class ToolStatusArgs(BaseModel):
    server: str = Field(max_length=64)
    tool: str = Field(max_length=100)
    status: Literal["on", "off"]


class ChangeDecision(BaseModel):
    change_id: int
    approve: bool


class AuditArgs(BaseModel):
    limit: int = Field(100, ge=1, le=1000)
    outcome: Literal["ok", "denied", "error"] | None = None
    caller_id: str | None = Field(None, max_length=200)


def _gateway(ctx: ToolContext):
    return ctx.services["gateway"]


@server.tool(callers=CALLERS, roles=ROLES)
async def list_sources(args, ctx: ToolContext) -> dict:
    """Each source with its team, URL, secret name, last sync, last good sync, error and project count."""
    async with session_scope() as session:
        status = await sync_status(session)
        rows = {s.id: s for s in (await session.scalars(select(Source))).all()}
    for s in status["sources"]:
        row = rows.get(s["id"])
        s["base_url"] = row.base_url if row else ""
        s["secret_ref"] = row.secret_ref if row else ""  # the name in the secret store, never the secret
        s["enabled"] = row.enabled if row else False
    return status


@server.tool(callers=CALLERS, roles=ROLES, input_model=SourceArg)
async def test_source(args: SourceArg, ctx: ToolContext) -> dict:
    """Check that a source can be read now (lists its projects, changes nothing)."""
    reader = GatewayReader(_gateway(ctx), ADAPTER)
    try:
        listing = await reader.call(args.source, "list_projects", {"fields": ["count"]})
    except SourceCallError as e:
        return {"source": args.source, "ok": False, "error": str(e)}
    return {"source": args.source, "ok": True, "projects_found": listing.get("count")}


@server.tool(callers=CALLERS, roles=ROLES, input_model=OptionalSource, read_only=False)
async def run_sync(args: OptionalSource, ctx: ToolContext) -> dict:
    """Sync now: read one or all sources and recompute health. Reads trackers only; never writes to them."""
    reader = GatewayReader(_gateway(ctx), ADAPTER)
    summary = await sync_all(reader, ctx.settings, today_in(ctx.settings), args.source)
    return summary.as_dict()


@server.tool(callers=CALLERS, roles=ROLES)
async def list_prefixes(args, ctx: ToolContext) -> dict:
    """Approved project code prefixes, whether each is active, and how many projects use it."""
    async with session_scope() as session:
        counts = dict((await session.execute(select(Project.prefix, func.count()).group_by(Project.prefix))).all())
        rows = (await session.scalars(select(Prefix).order_by(Prefix.value))).all()
        return {"prefixes": [{"value": p.value, "description": p.description, "active": p.active,
                              "projects": counts.get(p.value, 0)} for p in rows]}


@server.tool(callers=CALLERS, roles=ROLES, input_model=NewPrefix, read_only=False)
async def add_prefix(args: NewPrefix, ctx: ToolContext) -> dict:
    """Add an approved prefix. Projects named with it are picked up from the next sync."""
    async with session_scope() as session:
        if await session.scalar(select(Prefix).where(Prefix.value == args.value)):
            raise ToolError(f"Prefix {args.value} already exists")
        session.add(Prefix(value=args.value, description=args.description, active=True))
    return {"added": args.value}


@server.tool(callers=CALLERS, roles=ROLES, input_model=PrefixActive, read_only=False)
async def set_prefix_active(args: PrefixActive, ctx: ToolContext) -> dict:
    """Turn a prefix on or off. Off: its projects are not picked up from the next sync."""
    async with session_scope() as session:
        row = await session.scalar(select(Prefix).where(Prefix.value == args.value))
        if row is None:
            raise ToolError(f"No prefix {args.value}")
        row.active = args.active
    return {"value": args.value, "active": args.active}


@server.tool(callers=CALLERS, roles=ROLES)
async def get_settings(args, ctx: ToolContext) -> dict:
    """Sync schedule, Radar rules (thresholds), approvers, weekly digest, alerts and channels."""
    async with session_scope() as session:
        return (await appsettings.load(session, ctx.settings)).model_dump()


@server.tool(callers=CALLERS, roles=ROLES, input_model=SettingsChanges, read_only=False)
async def update_settings(args: SettingsChanges, ctx: ToolContext) -> dict:
    """Change one or more settings. Values are checked; nothing is saved if one is wrong."""
    try:
        async with session_scope() as session:
            result = await appsettings.update(session, ctx.settings, args.changes, ctx.caller.id)
    except ValidationError as e:
        err = e.errors()[0]
        raise ToolError(f"{'.'.join(str(x) for x in err['loc'])}: {err['msg']}") from e
    except ValueError as e:
        raise ToolError(str(e)) from e
    return result.model_dump()


@server.tool(callers=CALLERS, roles=ROLES, input_model=SyncLogArgs)
async def get_sync_log(args: SyncLogArgs, ctx: ToolContext) -> dict:
    """Sync runs, newest first: source, start, duration, projects read, result and errors."""
    async with session_scope() as session:
        q = select(SyncRun).order_by(SyncRun.id.desc()).limit(args.limit)
        if args.source:
            q = q.where(SyncRun.source_id == args.source)
        rows = (await session.scalars(q)).all()
        names = {s.id: s.name for s in (await session.scalars(select(Source))).all()}
    return {"runs": [{
        "id": r.id, "source": r.source_id, "source_name": names.get(r.source_id, r.source_id),
        "started_at": r.started_at.isoformat(), "ended_at": r.ended_at.isoformat() if r.ended_at else None,
        "duration_seconds": round((r.ended_at - r.started_at).total_seconds(), 1) if r.ended_at else None,
        "projects_read": r.projects_read, "result": r.result, "errors": r.errors_json,
    } for r in rows]}


@server.tool(callers=CALLERS, roles=ROLES)
async def get_non_compliant(args, ctx: ToolContext) -> dict:
    """Projects found in a tracker but skipped because the name has no approved prefix."""
    async with session_scope() as session:
        rows = (await session.scalars(select(NonCompliant).order_by(NonCompliant.source_id))).all()
        sources = {s.id: s for s in (await session.scalars(select(Source))).all()}
    return {"count": len(rows), "projects": [{
        "name_in_tracker": r.name_in_tracker, "source": r.source_id,
        "source_name": sources[r.source_id].name if r.source_id in sources else r.source_id,
        "team": sources[r.source_id].team if r.source_id in sources else "", "reason": r.reason,
        "seen_at": r.seen_at.isoformat()} for r in rows]}


@server.tool(callers=CALLERS, roles=ROLES)
async def list_tools(args, ctx: ToolContext) -> dict:
    """Every MCP tool in the registry: server, status (on, off, review), callers and roles."""
    async with session_scope() as session:
        rows = (await session.scalars(select(McpTool).order_by(McpTool.server, McpTool.name))).all()
    return {"tools": [{"server": r.server, "tool": r.name, "status": r.status, "callers": r.callers,
                       "roles": r.roles, "read_only": r.read_only, "description": r.description,
                       "changed_by": r.status_changed_by} for r in rows]}


@server.tool(callers=CALLERS, roles=ROLES, input_model=ToolStatusArgs, read_only=False)
async def set_tool_status(args: ToolStatusArgs, ctx: ToolContext) -> dict:
    """Turn a tool on or off. A tool waiting for review must have its change approved first."""
    registry = _gateway(ctx).registry
    try:
        async with session_scope() as session:
            await registry.set_status(session, args.server, args.tool, args.status, by=ctx.caller.id)
    except (KeyError, ValueError) as e:
        raise ToolError(str(e).strip("'\"")) from e
    return {"server": args.server, "tool": args.tool, "status": args.status}


@server.tool(callers=CALLERS, roles=ROLES)
async def list_tool_changes(args, ctx: ToolContext) -> dict:
    """Tools whose description, inputs or access rules changed and wait for approval, with the difference."""
    async with session_scope() as session:
        rows = (await session.scalars(select(McpToolChange).where(McpToolChange.status == "pending"))).all()
        tools = {t.id: t for t in (await session.scalars(select(McpTool))).all()}
    return {"changes": [{"id": c.id, "server": tools[c.tool_id].server, "tool": tools[c.tool_id].name,
                         "diff": c.diff, "created_at": c.created_at.isoformat()} for c in rows]}


@server.tool(callers=CALLERS, roles=ROLES, input_model=ChangeDecision, read_only=False)
async def decide_tool_change(args: ChangeDecision, ctx: ToolContext) -> dict:
    """Approve or reject a pending tool change. Approve turns the tool on; reject turns it off."""
    registry = _gateway(ctx).registry
    try:
        async with session_scope() as session:
            await registry.decide_change(session, args.change_id, args.approve, by=ctx.caller.id)
    except (KeyError, ValueError) as e:
        raise ToolError(str(e).strip("'\"")) from e
    return {"change_id": args.change_id, "approved": args.approve}


@server.tool(callers=CALLERS, roles=ROLES, input_model=AuditArgs, redact=False)  # admins must see who called
async def get_audit(args: AuditArgs, ctx: ToolContext) -> dict:
    """The audit log: every tool call by every caller, newest first."""
    async with session_scope() as session:
        q = select(McpCall).order_by(McpCall.id.desc()).limit(args.limit)
        if args.outcome:
            q = q.where(McpCall.outcome == args.outcome)
        if args.caller_id:
            q = q.where(McpCall.caller_id == args.caller_id)
        rows = (await session.scalars(q)).all()
    return {"calls": [{"at": r.at.isoformat(), "caller": f"{r.caller_kind}:{r.caller_id}", "server": r.server,
                       "tool": r.tool, "outcome": r.outcome, "reason": r.reason, "duration_ms": r.duration_ms}
                      for r in rows]}
