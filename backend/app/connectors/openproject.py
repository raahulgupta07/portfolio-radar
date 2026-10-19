"""Live OpenProject connector (API v3), read-only.

What each app field reads is set in Admin → field mapping (app/connectors/fields.py):
- project: an OpenProject project. Key = its identifier. Last update = updatedAt.
- status: the project status (On track, At risk, Finished…) or a project custom field.
- dates: earliest start and latest finish of its work packages, or two project custom fields.
- milestones: work packages whose type is a milestone.
- sprints: the project's versions (Backlogs). Active = today is between start and end.
- task counts: work packages; closed = done, open with an "in progress" status = in progress.
- links: "blocks" relations between work packages of different projects.
- risks: work packages of the risk type, with likelihood and impact custom fields.

Auth is an API key (HTTP Basic, user "apikey"). Only GET is used.
"""

from __future__ import annotations

import base64
import json
from collections.abc import Callable
from datetime import date, datetime
from typing import Any

from app.connectors import fields as fm
from app.connectors.base import (
    ProjectRef,
    SourceLink,
    SourceMilestone,
    SourceProject,
    SourceRisk,
    SourceSprint,
    SourceUnavailable,
    TaskCounts,
)
from app.connectors.http import ReadOnlyHttpClient

PAGE = 200


def auth_headers(token: str) -> dict[str, str]:
    raw = base64.b64encode(f"apikey:{token}".encode()).decode()
    return {"Authorization": f"Basic {raw}", "Accept": "application/hal+json"}


def _date(v: Any) -> date | None:
    try:
        return date.fromisoformat(v[:10]) if isinstance(v, str) and v else None
    except ValueError:
        return None


def _id(href: str | None) -> str | None:
    return href.rstrip("/").rsplit("/", 1)[-1] if href else None


def _filters(*items: dict[str, Any]) -> str:
    return json.dumps(list(items), separators=(",", ":"))


def custom_value(el: dict[str, Any], name: str) -> Any:
    """A custom field's value: plain (text, number, date), formattable ({raw}), or a link (list, user)."""
    if name in el:
        v = el[name]
        return v.get("raw") if isinstance(v, dict) else v
    link = (el.get("_links") or {}).get(name)
    if isinstance(link, list):
        return [x.get("title") for x in link if x.get("title")]
    if isinstance(link, dict):
        return link.get("title")
    return None


class OpenProjectConnector:
    def __init__(self, client: ReadOnlyHttpClient, *, base_url: str, fields: fm.OpenProjectFields,
                 aspirations: list[str], today: Callable[[], date] = date.today) -> None:
        self.source_id = "openproject"
        self.client = client
        self.base_url = base_url.rstrip("/")
        self.f = fields
        self.aspirations = aspirations
        self.today = today
        self._statuses: dict[str, dict[str, Any]] | None = None
        self._types: dict[str, dict[str, Any]] | None = None

    async def collection(self, path: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        offset = 1
        while True:
            page = await self.client.get_json(path, {**(params or {}), "pageSize": PAGE, "offset": offset})
            els = (page.get("_embedded") or {}).get("elements", [])
            out += els
            if not els or len(out) >= page.get("total", 0):
                return out
            offset += 1

    async def total(self, path: str, filters: str) -> int:
        page = await self.client.get_json(path, {"filters": filters, "pageSize": 1})
        return int(page.get("total", 0))

    async def statuses(self) -> dict[str, dict[str, Any]]:
        if self._statuses is None:
            self._statuses = {str(s["id"]): s for s in await self.collection("/api/v3/statuses")}
        return self._statuses

    async def types(self) -> dict[str, dict[str, Any]]:
        if self._types is None:
            self._types = {str(t["id"]): t for t in await self.collection("/api/v3/types")}
        return self._types

    # -- projects ----------------------------------------------------------------

    def _ref(self, p: dict[str, Any]) -> ProjectRef:
        updated = p.get("updatedAt")
        return ProjectRef(key=p["identifier"], name=p["name"], url=f"{self.base_url}/projects/{p['identifier']}",
                          updated_at=datetime.fromisoformat(updated.replace("Z", "+00:00")) if updated else None)

    async def list_projects(self) -> list[ProjectRef]:
        projects = await self.collection("/api/v3/projects", {"filters": _filters({"active": {"operator": "=", "values": ["t"]}})})
        return [self._ref(p) for p in projects]

    def _wp_path(self, key: str) -> str:
        return f"/api/v3/projects/{key}/work_packages"

    async def get_project(self, key: str) -> SourceProject:
        p = await self.client.get_json(f"/api/v3/projects/{key}")
        if self.f.status_from == "project_status":
            status = ((p.get("_links") or {}).get("status") or {}).get("title")
        else:
            status = custom_value(p, self.f.status_from)
        if not status or not isinstance(status, str):
            raise SourceUnavailable(f"OpenProject: {key} has no status where the field mapping says to look")
        owner = custom_value(p, self.f.owner_field) if self.f.owner_field else None
        if self.f.dates_from == "work_packages":
            start, end = await self._wp_dates(key)
        else:
            a, b = self.f.dates_from.split(",")
            start, end = _date(custom_value(p, a)), _date(custom_value(p, b))
        counts = await self.get_task_counts(key)
        return SourceProject(
            **self._ref(p).model_dump(), owner=owner if isinstance(owner, str) else None, status=status,
            start_date=start, end_date=end,
            percent_done=round(100 * counts.done / counts.total) if counts.total else None,
            strategy_tag=fm.aspiration(custom_value(p, self.f.strategy_field), self.aspirations) if self.f.strategy_field else None,
        )

    async def _wp_dates(self, key: str) -> tuple[date | None, date | None]:
        every = _filters({"status": {"operator": "*", "values": []}})
        first = await self.client.get_json(self._wp_path(key), {"filters": every, "pageSize": 1,
                                                                "sortBy": json.dumps([["startDate", "asc"]])})
        last = await self.client.get_json(self._wp_path(key), {"filters": every, "pageSize": 1,
                                                               "sortBy": json.dumps([["dueDate", "desc"]])})
        f = (first.get("_embedded") or {}).get("elements", [])
        la = (last.get("_embedded") or {}).get("elements", [])
        return (_date(f[0].get("startDate") or f[0].get("date")) if f else None,
                _date(la[0].get("dueDate") or la[0].get("date")) if la else None)

    async def get_milestones(self, key: str) -> list[SourceMilestone]:
        ids = [i for i, t in (await self.types()).items() if t.get("isMilestone")]
        if not ids:
            return []
        statuses = await self.statuses()
        wps = await self.collection(self._wp_path(key), {"filters": _filters(
            {"type": {"operator": "=", "values": ids}}, {"status": {"operator": "*", "values": []}})})
        out = []
        for w in wps:
            st = statuses.get(_id(((w.get("_links") or {}).get("status") or {}).get("href")) or "", {})
            out.append(SourceMilestone(name=w["subject"], due_date=_date(w.get("date") or w.get("dueDate")),
                                       status="done" if st.get("isClosed") else "open"))
        return out

    async def get_sprints(self, key: str) -> list[SourceSprint]:
        versions = await self.collection(f"/api/v3/projects/{key}/versions")
        today = self.today()
        out = []
        for v in versions:
            start, end = _date(v.get("startDate")), _date(v.get("endDate"))
            if v.get("status") == "closed" or (end and end < today):
                continue
            state = "active" if start and start <= today else "future"
            goal = (v.get("description") or {}).get("raw") or None
            out.append(SourceSprint(name=v["name"], goal=goal, start_date=start, end_date=end, state=state))
        return out

    async def get_task_counts(self, key: str) -> TaskCounts:
        statuses = await self.statuses()
        doing_ids = [i for i, s in statuses.items()
                     if not s.get("isClosed") and s.get("name", "").lower() in {x.lower() for x in self.f.in_progress_statuses}]
        path = self._wp_path(key)
        total = await self.total(path, _filters({"status": {"operator": "*", "values": []}}))
        done = await self.total(path, _filters({"status": {"operator": "c", "values": []}}))
        doing = await self.total(path, _filters({"status": {"operator": "=", "values": doing_ids}})) if doing_ids else 0
        return TaskCounts(todo=max(0, total - done - doing), in_progress=doing, done=done, total=total)

    async def get_links(self) -> list[SourceLink]:
        rels = await self.collection("/api/v3/relations", {"filters": _filters({"type": {"operator": "=", "values": ["blocks"]}})})
        pairs: list[tuple[str, str]] = []
        for r in rels:
            links = r.get("_links") or {}
            a, b = _id((links.get("from") or {}).get("href")), _id((links.get("to") or {}).get("href"))
            if a and b:
                pairs.append((a, b) if r.get("type", "blocks") == "blocks" else (b, a))
        if not pairs:
            return []
        wp_ids = sorted({x for p in pairs for x in p})
        project_of: dict[str, str] = {}
        for i in range(0, len(wp_ids), 100):
            chunk = wp_ids[i:i + 100]
            wps = await self.collection("/api/v3/work_packages", {"filters": _filters(
                {"id": {"operator": "=", "values": chunk}}, {"status": {"operator": "*", "values": []}})})
            for w in wps:
                project_of[str(w["id"])] = _id(((w.get("_links") or {}).get("project") or {}).get("href")) or ""
        ident = {str(p["id"]): p["identifier"] for p in await self.collection("/api/v3/projects")}
        seen = set()
        for a, b in pairs:
            pa, pb = ident.get(project_of.get(a, "")), ident.get(project_of.get(b, ""))
            if pa and pb and pa != pb:
                seen.add((pa, pb))
        return [SourceLink(from_key=a, to_key=b) for a, b in sorted(seen)]

    async def get_risks(self, key: str | None = None) -> list[SourceRisk]:
        if not (self.f.risk_type and self.f.likelihood_field and self.f.impact_field):
            return []
        type_ids = [i for i, t in (await self.types()).items() if t.get("name", "").lower() == self.f.risk_type.lower()]
        if not type_ids:
            return []
        path = self._wp_path(key) if key else "/api/v3/work_packages"
        wps = await self.collection(path, {"filters": _filters({"type": {"operator": "=", "values": type_ids}},
                                                               {"status": {"operator": "o", "values": []}})})
        ident = {str(p["id"]): p["identifier"] for p in await self.collection("/api/v3/projects")} if not key else {}
        out = []
        for w in wps:
            lk = fm.level(custom_value(w, self.f.likelihood_field))
            im = fm.level(custom_value(w, self.f.impact_field))
            if lk is None or im is None:
                continue
            links = w.get("_links") or {}
            project = key or ident.get(_id((links.get("project") or {}).get("href")) or "")
            out.append(SourceRisk(project_key=project, title=w["subject"], likelihood=lk, impact=im,
                                  owner=(links.get("assignee") or {}).get("title")))
        return out
