"""Where each app field comes from in a tracker (Admin → Connections → <source> → field mapping).

Trackers do not have one fixed place for a project's status, dates, owner or
strategy tag; each company sets them up its own way. So the live connectors
read them from places an admin names here. The defaults are a proposal only:
a live connector refuses to run until an admin has confirmed the mapping, so
nothing is guessed silently.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal, get_args, get_origin

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.app import Setting

FIELD_ID = r"^$|^[A-Za-z][A-Za-z0-9_]{0,63}$"
LEVELS = ("Low", "Medium", "High")


class JiraFields(BaseModel):
    anchor_jql: str = Field(
        'project = "{key}" AND issuetype = Epic AND labels = portfolio ORDER BY created ASC', max_length=500,
        description="Finds the one issue per project that holds its status and dates. {key} is the project key. "
                    "Empty = no such issue (status comes from the project category)")
    status_from: Literal["anchor", "category"] = Field(
        "anchor", description="anchor: the anchor issue's status. category: the project's category name")
    owner_from: Literal["lead", "anchor_assignee"] = Field("lead", description="The project lead, or the anchor issue's assignee")
    start_date_field: str = Field("customfield_10015", pattern=FIELD_ID,
                                  description="Field on the anchor issue with the start date (Cloud's 'Start date' is often customfield_10015)")
    end_date_field: str = Field("duedate", pattern=FIELD_ID, description="Field on the anchor issue with the end date")
    percent_done: str = Field("tasks", pattern=r"^tasks$|^[A-Za-z][A-Za-z0-9_]{0,63}$",
                              description="tasks: done tasks ÷ all tasks. Or a number field on the anchor issue")
    strategy_field: str = Field("", pattern=FIELD_ID,
                                description="Field (on the anchor issue) with the 2030 aspiration, e.g. labels or customfield_10100. Empty = none")
    task_jql: str = Field('project = "{key}" AND issuetype not in (Epic)', max_length=500,
                          description="Which issues count as the project's tasks")
    risk_jql: str = Field("labels = risk AND statusCategory != Done", max_length=500,
                          description="Which issues are risks, across all projects")
    likelihood_field: str = Field("", pattern=FIELD_ID, description="Risk likelihood field (Low/Medium/High). Empty = risks are not read")
    impact_field: str = Field("", pattern=FIELD_ID, description="Risk impact field (Low/Medium/High). Empty = risks are not read")
    links_jql: str = Field("issueLinkType = blocks", max_length=500,
                           description="Issues whose 'blocks' links become project dependencies")


class OpenProjectFields(BaseModel):
    status_from: str = Field("project_status", pattern=r"^project_status$|^customField[0-9]{1,6}$",
                             description="project_status: OpenProject's project status (On track, Finished…). Or a project custom field")
    owner_field: str = Field("", pattern=r"^$|^customField[0-9]{1,6}$", description="Project custom field (user) for the owner. Empty = none")
    dates_from: str = Field("work_packages", pattern=r"^work_packages$|^customField[0-9]{1,6},customField[0-9]{1,6}$",
                            description="work_packages: earliest start and latest finish of its work packages. "
                                        "Or two project custom fields 'customField1,customField2'")
    percent_done: Literal["tasks"] = Field("tasks", description="Closed work packages ÷ all work packages")
    strategy_field: str = Field("", pattern=r"^$|^customField[0-9]{1,6}$", description="Project custom field with the 2030 aspiration")
    in_progress_statuses: list[str] = Field(default_factory=lambda: ["In progress"], max_length=30,
                                            description="Open statuses counted as 'in progress' (the rest are 'to do')")
    risk_type: str = Field("Risk", max_length=60, description="Work package type used for risks. Empty = risks are not read")
    likelihood_field: str = Field("", pattern=r"^$|^customField[0-9]{1,6}$", description="Work package custom field for likelihood")
    impact_field: str = Field("", pattern=r"^$|^customField[0-9]{1,6}$", description="Work package custom field for impact")


MODELS: dict[str, type[BaseModel]] = {"jira": JiraFields, "openproject": OpenProjectFields}


class FieldMapping(BaseModel):
    source: str
    fields: dict[str, Any]
    confirmed_by: str | None = None
    confirmed_at: str | None = None

    @property
    def confirmed(self) -> bool:
        return self.confirmed_by is not None


def key(source_id: str) -> str:
    return f"fields.{source_id}"


def describe(source_id: str) -> list[dict[str, Any]]:
    """Each field with its default and help, for the Admin form."""
    model = MODELS[source_id]
    out = []
    for n, f in model.model_fields.items():
        options = list(get_args(f.annotation)) if get_origin(f.annotation) is Literal else None
        kind = "list" if get_origin(f.annotation) is list else "choice" if options else "text"
        out.append({"field": n, "default": f.default if f.default_factory is None else f.default_factory(),
                    "help": f.description or "", "kind": kind, "options": options})
    return out


async def load(session: AsyncSession, source_id: str) -> FieldMapping | None:
    if source_id not in MODELS:
        return None
    row = await session.get(Setting, key(source_id))
    if row is None:
        return FieldMapping(source=source_id, fields=MODELS[source_id]().model_dump())
    value = dict(row.value)
    fields = MODELS[source_id].model_validate(value.get("fields", {})).model_dump()
    return FieldMapping(source=source_id, fields=fields, confirmed_by=value.get("confirmed_by"),
                        confirmed_at=value.get("confirmed_at"))


async def save(session: AsyncSession, source_id: str, fields: dict[str, Any], by: str, confirm: bool) -> FieldMapping:
    """Saving a change without confirming clears an earlier confirmation, so a live sync waits for a person to check it."""
    clean = MODELS[source_id].model_validate(fields).model_dump()
    m = FieldMapping(source=source_id, fields=clean)
    if confirm:
        m.confirmed_by, m.confirmed_at = by, datetime.now(UTC).isoformat()
    value = m.model_dump(exclude={"source"})
    row = await session.get(Setting, key(source_id))
    if row is None:
        session.add(Setting(key=key(source_id), value=value, updated_by=by))
    else:
        row.value, row.updated_by = value, by
    return m


def level(value: Any) -> str | None:
    """A tracker value as Low/Medium/High, or None if it is something else (never guessed)."""
    if isinstance(value, dict):
        value = value.get("value") or value.get("name") or value.get("title")
    if not isinstance(value, str):
        return None
    v = value.strip().lower()
    return next((x for x in LEVELS if x.lower() == v), None)


def aspiration(value: Any, aspirations: list[str]) -> str | None:
    """The first value that names a 2030 aspiration (ignoring case, spaces and dashes)."""
    def norm(s: str) -> str:
        return "".join(ch for ch in s.lower() if ch.isalnum())

    wanted = {norm(a): a for a in aspirations}
    items = value if isinstance(value, list) else [value]
    for item in items:
        if isinstance(item, dict):
            item = item.get("value") or item.get("name") or item.get("title")
        if isinstance(item, str) and norm(item) in wanted:
            return wanted[norm(item)]
    return None
