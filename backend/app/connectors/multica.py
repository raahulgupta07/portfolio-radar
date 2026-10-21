"""Live Multica connector (REST API), read-only.

Multica groups work in workspaces. A personal access token (`mul_...`) sees every workspace its user belongs
to, so one read-only service user can feed the portfolio from all of them. Every call is a GET.

What each app field reads (set in Admin → field mapping, app/connectors/fields.py):
- project: a Multica project. Key = "<workspace id>/<project id>". Name = its title. Last update = updated_at.
- status: the project's own status (planned, in_progress, completed), mapped by the adapter's status map.
- owner: the project lead, looked up in the workspace's members (or agents).
- dates: the project's start_date and due_date.
- % done: done_count ÷ issue_count, the numbers Multica shows (cancelled issues count as done).
- milestones: Multica has no milestone object. A select property on issues (default "Milestone") names it; its
  due date is the latest due date among the issues that carry it, and it is done when all of them are done.
- task counts: the project's issues; done and cancelled = done, the mapped statuses = in progress, the rest = to do.
- sprints and links: not available in Multica's data, so none are returned.
- risks: issues carrying the risk label, with likelihood and impact from two select properties. Off until mapped.
"""

from __future__ import annotations

import time
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

PAGE = 100  # Multica returns at most 100 items per call
MAX_PAGES = 200  # a tracker that never ends its list cannot stall the sync
CACHE_SECONDS = 300.0  # one sync reads many projects; reload everything for the next night's run
DONE = frozenset({"done", "cancelled"})


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Accept": "application/json"}


def _date(v: Any) -> date | None:
    try:
        return date.fromisoformat(v[:10]) if isinstance(v, str) and v else None
    except ValueError:
        return None


def _dt(v: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(v.replace("Z", "+00:00")) if isinstance(v, str) and v else None
    except ValueError:
        return None


class MulticaConnector:
    def __init__(self, client: ReadOnlyHttpClient, *, base_url: str, fields: fm.MulticaFields,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self.source_id = "multica"
        self.client = client
        self.base_url = base_url.rstrip("/")
        self.f = fields
        self.clock = clock
        self._workspaces_at = -1e9
        self._workspaces: list[dict[str, Any]] = []
        self._bundles: dict[str, tuple[float, dict[str, Any]]] = {}

    # -- reading ---------------------------------------------------------------------

    async def workspaces(self) -> list[dict[str, Any]]:
        if self.clock() - self._workspaces_at >= CACHE_SECONDS:
            data = await self.client.get_json("/api/workspaces")
            if not isinstance(data, list):
                raise SourceUnavailable("Multica: unexpected answer for the workspace list")
            wanted = {w.strip().lower() for w in self.f.workspaces if w.strip()}
            chosen = [w for w in data if not wanted or str(w.get("slug", "")).lower() in wanted or str(w.get("id", "")).lower() in wanted]
            if wanted and not chosen:
                raise SourceUnavailable("Multica: none of the workspaces in the field mapping were found for this token")
            self._workspaces, self._workspaces_at = chosen, self.clock()
        return self._workspaces

    async def _list(self, path: str, wid: str, key: str) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        seen: set[Any] = set()
        for _ in range(MAX_PAGES):
            data = await self.client.get_json(path, {"workspace_id": wid, "limit": PAGE, "offset": len(out)})
            items = data.get(key, []) if isinstance(data, dict) else data
            fresh = [x for x in items if x.get("id") not in seen]
            if not fresh:
                break
            seen.update(x.get("id") for x in fresh)
            out += fresh
            total = data.get("total") if isinstance(data, dict) else None
            if len(items) < PAGE or (isinstance(total, int) and len(out) >= total):
                break
        return out

    async def _bundle(self, wid: str) -> dict[str, Any]:
        """Everything one workspace holds that a sync needs, read once and reused for the whole run."""
        hit = self._bundles.get(wid)
        if hit and self.clock() - hit[0] < CACHE_SECONDS:
            return hit[1]
        props = await self.client.get_json("/api/properties", {"workspace_id": wid})
        agents = await self.client.get_json("/api/agents", {"workspace_id": wid})
        members = await self.client.get_json(f"/api/workspaces/{wid}/members")
        bundle = {
            "projects": await self._list("/api/projects", wid, "projects"),
            "issues": await self._list("/api/issues", wid, "issues"),
            "properties": props.get("properties", []) if isinstance(props, dict) else [],
            "names": self._names(members, agents),
        }
        self._bundles[wid] = (self.clock(), bundle)
        return bundle

    @staticmethod
    def _names(members: Any, agents: Any) -> dict[str, str]:
        names: dict[str, str] = {}
        for a in agents if isinstance(agents, list) else []:
            names[str(a.get("id"))] = a.get("name") or ""
        for m in members if isinstance(members, list) else []:
            for k in ("id", "user_id"):
                if m.get(k):
                    names[str(m[k])] = m.get("name") or ""
        return names

    async def _project(self, key: str) -> tuple[str, dict[str, Any], dict[str, Any]]:
        wid, _, pid = key.partition("/")
        if not wid or not pid:
            raise SourceUnavailable(f"Multica: '{key}' is not a project key (expected workspace/project)")
        bundle = await self._bundle(wid)
        project = next((p for p in bundle["projects"] if p.get("id") == pid), None)
        if project is None:
            raise SourceUnavailable(f"Multica: project {key} was not found")
        return wid, bundle, project

    def _issues(self, bundle: dict[str, Any], pid: str) -> list[dict[str, Any]]:
        return [i for i in bundle["issues"] if i.get("project_id") == pid]

    @staticmethod
    def _property(bundle: dict[str, Any], name: str) -> dict[str, Any] | None:
        if not name:
            return None
        return next((p for p in bundle["properties"] if str(p.get("name", "")).lower() == name.lower() and p.get("type") == "select"), None)

    # -- the connector interface -----------------------------------------------------

    async def list_projects(self) -> list[ProjectRef]:
        out = []
        for w in await self.workspaces():
            for p in (await self._bundle(w["id"]))["projects"]:
                out.append(ProjectRef(key=f"{w['id']}/{p['id']}", name=p["title"], updated_at=_dt(p.get("updated_at"))))
        return out

    async def get_project(self, key: str) -> SourceProject:
        _, bundle, p = await self._project(key)
        if not p.get("status"):
            raise SourceUnavailable(f"Multica: {p.get('title', key)} has no status")
        total, done = p.get("issue_count") or 0, p.get("done_count") or 0
        lead = bundle["names"].get(str(p.get("lead_id"))) if p.get("lead_id") else None
        return SourceProject(
            key=key, name=p["title"], updated_at=_dt(p.get("updated_at")), owner=lead or None, status=p["status"],
            start_date=_date(p.get("start_date")), end_date=_date(p.get("due_date")),
            percent_done=round(100 * done / total) if total else None,
        )

    async def get_milestones(self, key: str) -> list[SourceMilestone]:
        _, bundle, p = await self._project(key)
        prop = self._property(bundle, self.f.milestone_property)
        if prop is None:
            return []
        options = [(o["id"], o["name"]) for o in (prop.get("config") or {}).get("options", [])]
        groups: dict[str, list[dict[str, Any]]] = {}
        for i in self._issues(bundle, p["id"]):
            value = (i.get("properties") or {}).get(prop["id"])
            if isinstance(value, str):
                groups.setdefault(value, []).append(i)
        out = []
        for oid, name in options:
            issues = groups.get(oid)
            if not issues:
                continue
            dues = [d for d in (_date(i.get("due_date")) for i in issues) if d]
            out.append(SourceMilestone(name=name, due_date=max(dues) if dues else None,
                                       status="done" if all(i.get("status") in DONE for i in issues) else "open"))
        return out

    async def get_sprints(self, key: str) -> list[SourceSprint]:
        return []  # Multica has no sprint object in its data

    async def get_task_counts(self, key: str) -> TaskCounts:
        _, bundle, p = await self._project(key)
        doing = {s.lower() for s in self.f.in_progress_statuses}
        issues = self._issues(bundle, p["id"])
        done = sum(1 for i in issues if i.get("status") in DONE)
        in_progress = sum(1 for i in issues if i.get("status") not in DONE and str(i.get("status", "")).lower() in doing)
        return TaskCounts(todo=len(issues) - done - in_progress, in_progress=in_progress, done=done, total=len(issues))

    async def get_links(self) -> list[SourceLink]:
        return []  # Multica's issue fields hold no "blocks" relation between projects

    async def get_risks(self, key: str | None = None) -> list[SourceRisk]:
        f = self.f
        if not (f.risk_label and f.likelihood_property and f.impact_property):
            return []
        out = []
        for w in await self.workspaces():
            if key and not key.startswith(f"{w['id']}/"):
                continue
            bundle = await self._bundle(w["id"])
            like, impact = self._property(bundle, f.likelihood_property), self._property(bundle, f.impact_property)
            if like is None or impact is None:
                continue
            for i in bundle["issues"]:
                if i.get("status") in DONE or f.risk_label.lower() not in {str(lb.get("name", "")).lower() for lb in i.get("labels") or []}:
                    continue
                if key and f"{w['id']}/{i.get('project_id')}" != key:
                    continue
                lk, im = (self._level(like, i), self._level(impact, i))
                if lk is None or im is None:
                    continue
                out.append(SourceRisk(project_key=f"{w['id']}/{i['project_id']}" if i.get("project_id") else None, title=i["title"],
                                      likelihood=lk, impact=im, owner=bundle["names"].get(str(i.get("assignee_id"))) or None))
        return out

    @staticmethod
    def _level(prop: dict[str, Any], issue: dict[str, Any]) -> str | None:
        value = (issue.get("properties") or {}).get(prop["id"])
        name = next((o["name"] for o in (prop.get("config") or {}).get("options", []) if o.get("id") == value), None)
        return fm.level(name)
