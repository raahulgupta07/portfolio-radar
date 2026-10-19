"""`/portfolio/mcp`: everything the screens show and agents read, from our
database. Read-only. Every project row carries its source, sync time and a
`stale` flag, so answers can show their evidence."""

from typing import Literal

from pydantic import BaseModel, Field

from app.db import session_scope
from app.health import today_in
from app.mcp.guard import ToolError
from app.mcp.registry import ServerDef, ToolContext
from app.portfolio import queries

server = ServerDef(
    name="portfolio",
    title="Portfolio",
    description="City Holdings projects from JIRA, OpenProject and Multica, synced daily. Read-only.",
    owner="Portfolio owner (IT)",
    direction="out",
)

CALLERS = {"human", "agent", "service"}
ROLES = {"viewer", "agent", "radar"}  # people, agents, and the nightly Radar job

Health = Literal["on_track", "at_risk", "off_track", "done"]


class ProjectFilter(BaseModel):
    health: Health | None = None
    source: Literal["jira", "openproject", "multica"] | None = None
    prefix: str | None = Field(None, max_length=50)
    team: str | None = Field(None, max_length=100)
    status: Literal["Not started", "In progress", "Done", "On hold"] | None = None
    q: str | None = Field(None, max_length=100, description="Search in project code or name")


class Code(BaseModel):
    code: str = Field(min_length=3, max_length=64, description="Project code, e.g. CHL-DP-POS03")


class CodeWeeks(Code):
    weeks: int = Field(6, ge=1, le=52)


class OptionalCode(BaseModel):
    code: str | None = Field(None, max_length=64, description="Limit to one project (optional)")


@server.tool(callers=CALLERS, roles=ROLES)
async def get_overview(args, ctx: ToolContext) -> dict:
    """Portfolio overview in one call: health tiles with change since last week, sources with sync state,
    6-week progress trend, progress by project, next milestones, the project table and Radar's latest findings."""
    async with session_scope() as session:
        return await queries.overview(session, today_in(ctx.settings))


@server.tool(callers=CALLERS, roles=ROLES, input_model=ProjectFilter)
async def list_projects(args: ProjectFilter, ctx: ToolContext) -> dict:
    """List projects with health, source, status, progress, next milestone and strategy.
    Filter by health, source, prefix, team or status, or search by code or name."""
    async with session_scope() as session:
        return await queries.list_projects(session, args.model_dump(), today_in(ctx.settings))


@server.tool(callers=CALLERS, roles=ROLES, input_model=Code)
async def get_project(args: Code, ctx: ToolContext) -> dict:
    """One project in full: health and its reasons, tasks, milestones, current sprint, 6-week trend,
    what changed this week, risks, what it waits for and blocks, and a link to edit it in its source tool."""
    async with session_scope() as session:
        result = await queries.project_detail(session, args.code, today_in(ctx.settings))
    if result is None:
        raise ToolError(f"No project with code {args.code.upper()}")
    return result


@server.tool(callers=CALLERS, roles=ROLES, input_model=CodeWeeks)
async def get_history(args: CodeWeeks, ctx: ToolContext) -> dict:
    """Daily snapshots of one project's status, health and % done for the last N weeks."""
    async with session_scope() as session:
        result = await queries.history(session, args.code, args.weeks, today_in(ctx.settings))
    if result is None:
        raise ToolError(f"No project with code {args.code.upper()}")
    return result


@server.tool(callers=CALLERS, roles=ROLES)
async def get_roadmap(args, ctx: ToolContext) -> dict:
    """Timeline of all projects: start and end dates, milestones (overdue marked), today, and dependencies."""
    async with session_scope() as session:
        return await queries.roadmap(session, today_in(ctx.settings))


@server.tool(callers=CALLERS, roles=ROLES, input_model=OptionalCode)
async def get_dependencies(args: OptionalCode, ctx: ToolContext) -> dict:
    """'Blocks' links between projects, from tracker links and PMO records, for all projects or one."""
    async with session_scope() as session:
        return await queries.dependencies(session, args.code, today_in(ctx.settings))


@server.tool(callers=CALLERS, roles=ROLES, input_model=OptionalCode)
async def get_risks(args: OptionalCode, ctx: ToolContext) -> dict:
    """Risk register with likelihood and impact, a likelihood × impact matrix, and health by 2030 strategy tag."""
    async with session_scope() as session:
        return await queries.risks(session, args.code, ctx.settings.strategy_aspirations)


@server.tool(callers=CALLERS, roles=ROLES)
async def get_sync_status(args, ctx: ToolContext) -> dict:
    """Each source's last sync, last good sync, error and whether its data is stale."""
    async with session_scope() as session:
        return await queries.sync_status(session)
