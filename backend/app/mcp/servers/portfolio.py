"""`/portfolio/mcp`: everything the screens show and agents read, from our
database. Every project row carries its source, sync time and a `stale` flag, so
answers can show their evidence. Read-only, except four Admin-only tools that edit
the program office data in Radar's own po_* tables (never a tracker)."""

import base64
from datetime import datetime
from typing import Any, Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field

from app.db import session_scope
from app.health import today_in
from app.mcp.guard import ToolError
from app.mcp.pii import redact
from app.mcp.registry import ServerDef, ToolContext
from app.portfolio import onepager, programs, queries

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
async def get_programs(args, ctx: ToolContext) -> dict:
    """Program office view: each program with its charter, budget, milestones, measurables, team and steering
    committee, plus its projects with owner, RACI, next step and decision needed, and summary counts. Read-only."""
    async with session_scope() as session:
        return await programs.programs_view(session, today_in(ctx.settings))


class SaveRecord(BaseModel):
    data: dict[str, Any] = Field(description="The fields to save. Leave out `id` to add a new one")
    base_updated_at: str | None = Field(None, max_length=40, description="`updated_at` as the editor loaded it, to catch a lost edit")
    by_name: str | None = Field(None, max_length=100, description="Name of the person saving, shown in Activity")


class DeleteRecord(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    by_name: str | None = Field(None, max_length=100)


def _saver(ctx: ToolContext, by_name: str | None) -> str:
    who = (by_name or "").strip()
    return f"{who} ({ctx.caller.id})" if who else ctx.caller.id


def _payload(args: SaveRecord) -> dict[str, Any]:
    return {**args.data, **({"base_updated_at": args.base_updated_at} if args.base_updated_at is not None else {})}


@server.tool(callers={"human"}, roles={"admin"}, read_only=False, input_model=SaveRecord)
async def save_project(args: SaveRecord, ctx: ToolContext) -> dict:
    """Admin only. Add a program-office project (no id) or change one. Saved in Radar's own tables and logged in
    Activity with who made the change. Nothing is written to JIRA, OpenProject or Multica."""
    async with session_scope() as session:
        try:
            return await programs.save_project(session, _payload(args), _saver(ctx, args.by_name))
        except programs.SaveError as e:
            raise ToolError(str(e)) from e


@server.tool(callers={"human"}, roles={"admin"}, read_only=False, input_model=DeleteRecord)
async def delete_project(args: DeleteRecord, ctx: ToolContext) -> dict:
    """Admin only. Delete a program-office project from Radar's own tables and log it in Activity."""
    async with session_scope() as session:
        try:
            return await programs.delete_project(session, args.id, _saver(ctx, args.by_name))
        except programs.SaveError as e:
            raise ToolError(str(e)) from e


@server.tool(callers={"human"}, roles={"admin"}, read_only=False, input_model=SaveRecord)
async def save_program(args: SaveRecord, ctx: ToolContext) -> dict:
    """Admin only. Add a program (no id) or change a program's charter: dates, text, budget, milestones, measurables,
    team and steering committee. Saved in Radar's own tables and logged in Activity. Nothing goes to a tracker."""
    async with session_scope() as session:
        try:
            return await programs.save_program(session, _payload(args), _saver(ctx, args.by_name))
        except programs.SaveError as e:
            raise ToolError(str(e)) from e


@server.tool(callers={"human"}, roles={"admin"}, read_only=False, input_model=DeleteRecord)
async def delete_program(args: DeleteRecord, ctx: ToolContext) -> dict:
    """Admin only. Delete a program that has no projects left, from Radar's own tables, and log it in Activity."""
    async with session_scope() as session:
        try:
            return await programs.delete_program(session, args.id, _saver(ctx, args.by_name))
        except programs.SaveError as e:
            raise ToolError(str(e)) from e


@server.tool(callers=CALLERS, roles=ROLES)
async def get_sync_status(args, ctx: ToolContext) -> dict:
    """Each source's last sync, last good sync, error and whether its data is stale."""
    async with session_scope() as session:
        return await queries.sync_status(session)


# -- PDF one-pagers (FR-16) ----------------------------------------------------------

def _pdf(content: bytes, filename: str) -> dict:
    return {"filename": filename, "media_type": "application/pdf", "bytes": len(content),
            "content_base64": base64.b64encode(content).decode()}


@server.tool(callers={"human"}, roles={"viewer"}, input_model=Code, redact=False)
async def get_project_pdf(args: Code, ctx: ToolContext) -> dict:
    """One project as a one-page PDF (A4): health, % done, next milestone, Radar's note, milestones, sprint,
    trend, what changed, risks and dependencies. Returned as base64. Personal data is removed before drawing."""
    async with session_scope() as session:
        result = await queries.project_detail(session, args.code, today_in(ctx.settings))
    if result is None:
        raise ToolError(f"No project with code {args.code.upper()}")
    content = onepager.project_pdf(redact(result), datetime.now(ZoneInfo(ctx.settings.timezone)), ctx.caller.id)
    return _pdf(content, f"{result['code']}-one-pager.pdf")


@server.tool(callers={"human"}, roles={"viewer"}, redact=False)
async def get_overview_pdf(args, ctx: ToolContext) -> dict:
    """The whole portfolio as a one-page PDF (A4 landscape) for the Steering Committee: health counts with change,
    sources, 6-week trend, projects that need attention, next milestones and Radar's findings. Returned as base64."""
    today = today_in(ctx.settings)
    async with session_scope() as session:
        result = await queries.overview(session, today)
    content = onepager.overview_pdf(redact(result), datetime.now(ZoneInfo(ctx.settings.timezone)), ctx.caller.id)
    return _pdf(content, f"portfolio-{today.isoformat()}.pdf")

