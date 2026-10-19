"""One interface for every source tracker. Each connector maps its tracker's
API to these shapes, without interpreting them: prefix rules, status mapping
and health are the adapter's job (Phase 3)."""

from datetime import date, datetime
from typing import Protocol

from pydantic import BaseModel


class SourceUnavailable(Exception):
    """The source could not be read (network, auth, server error). The message is safe to show."""


class ProjectRef(BaseModel):
    key: str  # the tracker's own id
    name: str  # name as written in the tracker, code prefix included
    url: str | None = None
    updated_at: datetime | None = None


class SourceProject(ProjectRef):
    owner: str | None = None
    team: str | None = None
    status: str  # the tracker's own status value
    start_date: date | None = None
    end_date: date | None = None
    percent_done: int | None = None
    strategy_tag: str | None = None


class SourceMilestone(BaseModel):
    name: str
    due_date: date | None = None
    status: str = "open"
    completed_at: datetime | None = None


class SourceSprint(BaseModel):
    name: str
    goal: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    state: str = "active"


class TaskCounts(BaseModel):
    todo: int = 0
    in_progress: int = 0
    done: int = 0
    total: int = 0


class SourceLink(BaseModel):
    from_key: str
    to_key: str
    kind: str = "blocks"


class SourceRisk(BaseModel):
    project_key: str | None = None
    title: str
    likelihood: str
    impact: str
    owner: str | None = None


class Connector(Protocol):
    source_id: str

    async def list_projects(self) -> list[ProjectRef]: ...
    async def get_project(self, key: str) -> SourceProject: ...
    async def get_milestones(self, key: str) -> list[SourceMilestone]: ...
    async def get_sprints(self, key: str) -> list[SourceSprint]: ...
    async def get_task_counts(self, key: str) -> TaskCounts: ...
    async def get_links(self) -> list[SourceLink]: ...
    async def get_risks(self, key: str | None = None) -> list[SourceRisk]: ...
