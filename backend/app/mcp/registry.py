"""The registry: every MCP server and tool the gateway knows, with owner,
access rules and on/off status.

Tools are declared in code (see app/mcp/servers/). At start-up the gateway
writes them to the `mcp` schema:
- a new tool is stored as `off`. Its owner turns it on.
- a tool whose description, inputs or access rules changed in code moves to
  `review`, and a pending change is recorded. It cannot be used until the owner
  approves the change.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.mcp.identity import CALLER_KINDS, Caller, CallerKind
from app.models.mcp import McpServer, McpTool, McpToolChange
from app.settings import Settings


class NoArgs(BaseModel):
    """For tools that take no arguments."""


@dataclass
class ToolContext:
    caller: Caller
    settings: Settings
    services: dict[str, Any]


Handler = Callable[[Any, ToolContext], Awaitable[Any]]


@dataclass
class ToolSpec:
    server: str
    name: str
    description: str
    input_model: type[BaseModel]
    handler: Handler
    callers: frozenset[CallerKind]
    roles: frozenset[str]
    read_only: bool = True
    redact: bool = True
    secret_args: frozenset[str] = frozenset()  # never written to the audit log

    @property
    def key(self) -> str:
        return f"{self.server}.{self.name}"

    def input_schema(self) -> dict[str, Any]:
        schema = self.input_model.model_json_schema()
        schema.setdefault("type", "object")
        props = schema.setdefault("properties", {})
        props["fields"] = {
            "type": "array",
            "items": {"type": "string"},
            "description": "Optional. Return only these fields, e.g. [\"code\", \"health\"] or [\"projects[].code\"].",
        }
        return schema

    def code_hash(self) -> str:
        payload = {
            "description": self.description,
            "input_schema": self.input_schema(),
            "callers": sorted(self.callers),
            "roles": sorted(self.roles),
            "read_only": self.read_only,
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


@dataclass
class ServerDef:
    name: str
    title: str
    description: str
    owner: str
    direction: Literal["in", "out"]
    tools: dict[str, ToolSpec] = field(default_factory=dict)

    def tool(
        self,
        *,
        callers: set[CallerKind] | frozenset[CallerKind],
        roles: set[str] | frozenset[str] = frozenset(),
        input_model: type[BaseModel] = NoArgs,
        read_only: bool = True,
        redact: bool = True,
        secret_args: set[str] | frozenset[str] = frozenset(),
        name: str | None = None,
        description: str | None = None,
    ) -> Callable[[Handler], Handler]:
        bad = set(callers) - set(CALLER_KINDS)
        if bad or not callers:
            raise ValueError(f"{self.name}: callers must be a non-empty subset of {CALLER_KINDS}")

        def decorator(fn: Handler) -> Handler:
            tool_name = name or fn.__name__
            doc = description or (fn.__doc__ or "").strip()
            if not doc:
                raise ValueError(f"{self.name}.{tool_name}: a tool needs a description")
            if tool_name in self.tools:
                raise ValueError(f"{self.name}.{tool_name}: declared twice")
            self.tools[tool_name] = ToolSpec(
                server=self.name,
                name=tool_name,
                description=" ".join(doc.split()),
                input_model=input_model,
                handler=fn,
                callers=frozenset(callers),
                roles=frozenset(roles),
                read_only=read_only,
                redact=redact,
                secret_args=frozenset(secret_args),
            )
            return fn

        return decorator


@dataclass(frozen=True)
class ToolState:
    status: str
    approved_hash: str | None


class Registry:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.servers: dict[str, ServerDef] = {}
        self._state: dict[str, ToolState] = {}
        self._state_loaded_at = 0.0

    def add(self, server: ServerDef) -> None:
        if server.name in self.servers:
            raise ValueError(f"server {server.name} registered twice")
        self.servers[server.name] = server

    def get(self, server: str, tool: str) -> ToolSpec | None:
        s = self.servers.get(server)
        return s.tools.get(tool) if s else None

    def all_tools(self) -> list[ToolSpec]:
        return [t for s in self.servers.values() for t in s.tools.values()]

    # -- database -------------------------------------------------------------

    async def sync(self, session: AsyncSession) -> dict[str, list[str]]:
        """Write servers and tools from code to the registry tables.

        Returns what happened, for the start-up log: new tools (off) and
        changed tools (waiting for review).
        """
        report: dict[str, list[str]] = {"new": [], "review": []}
        existing_servers = {s.name: s for s in (await session.scalars(select(McpServer))).all()}
        for sdef in self.servers.values():
            row = existing_servers.get(sdef.name)
            if row is None:
                session.add(McpServer(name=sdef.name, title=sdef.title, description=sdef.description,
                                      owner=sdef.owner, direction=sdef.direction))
            else:
                row.title, row.description, row.owner, row.direction = sdef.title, sdef.description, sdef.owner, sdef.direction
        await session.flush()

        rows = {(t.server, t.name): t for t in (await session.scalars(select(McpTool))).all()}
        for spec in self.all_tools():
            h = spec.code_hash()
            row = rows.get((spec.server, spec.name))
            if row is None:
                session.add(McpTool(
                    server=spec.server, name=spec.name, description=spec.description,
                    input_schema=spec.input_schema(), callers=sorted(spec.callers), roles=sorted(spec.roles),
                    read_only=spec.read_only, approved_hash=h, code_hash=h, status="off",
                ))
                report["new"].append(spec.key)
                continue
            if row.code_hash == h:
                continue
            row.code_hash = h
            if row.approved_hash == h:
                continue  # changed back to the approved version
            row.status = "review"
            pending = await session.scalar(
                select(McpToolChange).where(McpToolChange.tool_id == row.id, McpToolChange.status == "pending"))
            diff = _diff(row, spec)
            if pending is None:
                session.add(McpToolChange(tool_id=row.id, old_hash=row.approved_hash, new_hash=h, diff=diff))
            else:
                pending.new_hash, pending.diff = h, diff
            report["review"].append(spec.key)
        await session.flush()
        self._state_loaded_at = 0.0
        return report

    async def state(self, session: AsyncSession, server: str, tool: str) -> ToolState | None:
        now = time.monotonic()
        if now - self._state_loaded_at > self.settings.registry_cache_seconds:
            rows = (await session.execute(select(McpTool.server, McpTool.name, McpTool.status, McpTool.approved_hash))).all()
            self._state = {f"{r.server}.{r.name}": ToolState(r.status, r.approved_hash) for r in rows}
            self._state_loaded_at = now
        return self._state.get(f"{server}.{tool}")

    def forget_cache(self) -> None:
        self._state_loaded_at = 0.0

    async def is_usable(self, session: AsyncSession, spec: ToolSpec) -> tuple[bool, str]:
        st = await self.state(session, spec.server, spec.name)
        if st is None:
            return False, "Tool is not in the registry yet"
        if st.status == "review" or st.approved_hash != spec.code_hash():
            return False, "Tool changed and is waiting for its owner to approve the change"
        if st.status != "on":
            return False, "Tool is switched off. Its owner must turn it on"
        return True, ""

    # -- owner actions (CLI now, /admin/mcp later) ----------------------------

    async def set_status(self, session: AsyncSession, server: str, tool: str, status: str, by: str) -> None:
        if status not in ("on", "off"):
            raise ValueError("status must be on or off")
        row = await session.scalar(select(McpTool).where(McpTool.server == server, McpTool.name == tool))
        if row is None:
            raise KeyError(f"{server}.{tool} is not in the registry")
        if row.status == "review" and status == "on":
            raise ValueError(f"{server}.{tool} has a pending change. Approve the change first")
        row.status, row.status_changed_by, row.status_changed_at = status, by, datetime.now(UTC)
        self.forget_cache()

    async def decide_change(self, session: AsyncSession, change_id: int, approve: bool, by: str) -> None:
        change = await session.get(McpToolChange, change_id)
        if change is None or change.status != "pending":
            raise KeyError(f"No pending change {change_id}")
        row = await session.get(McpTool, change.tool_id)
        assert row is not None
        now = datetime.now(UTC)
        change.status, change.decided_by, change.decided_at = ("approved" if approve else "rejected"), by, now
        if approve:
            spec = self.get(row.server, row.name)
            if spec is None or spec.code_hash() != change.new_hash:
                raise ValueError("The code changed again since this change was recorded. Restart to record it")
            row.description, row.input_schema = spec.description, spec.input_schema()
            row.callers, row.roles, row.read_only = sorted(spec.callers), sorted(spec.roles), spec.read_only
            row.approved_hash = change.new_hash
            row.status = "on"
        else:
            row.status = "off"
        row.status_changed_by, row.status_changed_at = by, now
        self.forget_cache()


def _diff(row: McpTool, spec: ToolSpec) -> dict[str, Any]:
    new = {"description": spec.description, "input_schema": spec.input_schema(), "callers": sorted(spec.callers),
           "roles": sorted(spec.roles), "read_only": spec.read_only}
    old = {"description": row.description, "input_schema": row.input_schema, "callers": row.callers,
           "roles": row.roles, "read_only": row.read_only}
    return {k: {"old": old[k], "new": new[k]} for k in new if old[k] != new[k]}
