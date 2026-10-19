"""Source servers: `/jira/mcp`, `/openproject/mcp`, `/multica/mcp`.

They wrap the read-only connector library. The nightly adapter (service, role
`adapter`) uses them to read the trackers; admins may use them to check live
data. Every tool is read-only.
"""

from pydantic import BaseModel, Field

from app.connectors import SOURCES
from app.connectors.base import Connector, SourceUnavailable
from app.mcp.guard import ToolError
from app.mcp.registry import ServerDef, ToolContext

CALLERS = {"service", "human"}
ROLES = {"adapter", "admin"}


class ProjectKey(BaseModel):
    key: str = Field(min_length=1, max_length=100, description="The project's id in the tracker")


class OptionalProjectKey(BaseModel):
    key: str | None = Field(default=None, max_length=100, description="Limit to one project (optional)")


def make_source_server(source_id: str) -> ServerDef:
    name, team = SOURCES[source_id]
    server = ServerDef(
        name=source_id,
        title=f"{name} (read-only)",
        description=f"Reads {name} ({team}) through its API. Read-only: no tool can change {name}.",
        owner="Portfolio owner (IT)",
        direction="in",
    )

    def connector(ctx: ToolContext) -> Connector:
        return ctx.services["connectors"][source_id]

    async def run(coro):
        try:
            return await coro
        except SourceUnavailable as e:
            raise ToolError(str(e)) from e

    @server.tool(callers=CALLERS, roles=ROLES,
                 description=f"List every project in {name}, with key, name as written in {name}, link and last update. "
                             "Includes projects without an approved code prefix.")
    async def list_projects(args, ctx: ToolContext) -> dict:
        projects = await run(connector(ctx).list_projects())
        return {"source": source_id, "count": len(projects), "projects": projects}

    @server.tool(callers=CALLERS, roles=ROLES, input_model=ProjectKey,
                 description=f"Get one {name} project: owner, team, status as {name} names it, dates, % done.")
    async def get_project(args: ProjectKey, ctx: ToolContext) -> dict:
        return (await run(connector(ctx).get_project(args.key))).model_dump(mode="json")

    @server.tool(callers=CALLERS, roles=ROLES, input_model=ProjectKey,
                 description=f"List the milestones of one {name} project, with due dates and status.")
    async def get_milestones(args: ProjectKey, ctx: ToolContext) -> dict:
        return {"key": args.key, "milestones": await run(connector(ctx).get_milestones(args.key))}

    @server.tool(callers=CALLERS, roles=ROLES, input_model=ProjectKey,
                 description=f"List the sprints of one {name} project, with goal, dates and state.")
    async def get_sprints(args: ProjectKey, ctx: ToolContext) -> dict:
        return {"key": args.key, "sprints": await run(connector(ctx).get_sprints(args.key))}

    @server.tool(callers=CALLERS, roles=ROLES, input_model=ProjectKey,
                 description=f"Count the tasks of one {name} project by status: to do, in progress, done, total.")
    async def get_task_counts(args: ProjectKey, ctx: ToolContext) -> dict:
        return {"key": args.key, **(await run(connector(ctx).get_task_counts(args.key))).model_dump()}

    @server.tool(callers=CALLERS, roles=ROLES,
                 description=f"List 'blocks' links between {name} projects.")
    async def get_links(args, ctx: ToolContext) -> dict:
        return {"source": source_id, "links": await run(connector(ctx).get_links())}

    @server.tool(callers=CALLERS, roles=ROLES, input_model=OptionalProjectKey,
                 description=f"List risks recorded in {name} (risk labels and blockers), for all projects or one.")
    async def get_risks(args: OptionalProjectKey, ctx: ToolContext) -> dict:
        return {"source": source_id, "risks": await run(connector(ctx).get_risks(args.key))}

    return server
