"""Live JIRA connector, Cloud (REST v3) and Data Center (REST v2), read-only.

What each app field reads is set in Admin → field mapping (app/connectors/fields.py):
- project: a JIRA project. Name, link, lead. Last update = last issue update (Cloud only).
- status, dates, strategy tag: the project's "anchor" issue (found with anchor_jql), or its category.
- milestones: the project's versions (fix versions). Released = done.
- sprints: active and future sprints on the project's scrum boards (Agile API).
- task counts: issues found with task_jql, by status category (To Do, In Progress, Done).
- links: issues found with links_jql whose "blocks" link points into another project.
- risks: issues found with risk_jql, with likelihood and impact fields.

Only GET is used. JIRA Cloud's issue search is GET /rest/api/3/search/jql;
Data Center's is GET /rest/api/2/search.
"""

from __future__ import annotations

import base64
from urllib.parse import quote
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

PAGE = 100
MAX_PAGES = 500  # a tracker that never says "last page" cannot stall the sync


def auth_headers(flavor: str, account: str, token: str) -> dict[str, str]:
    if flavor == "cloud":
        if not account:
            raise SourceUnavailable("JIRA: JIRA Cloud needs the service account's email with the API token")
        raw = base64.b64encode(f"{account}:{token}".encode()).decode()
        return {"Authorization": f"Basic {raw}", "Accept": "application/json"}
    return {"Authorization": f"Bearer {token}", "Accept": "application/json"}


def _date(v: Any) -> date | None:
    if not v or not isinstance(v, str):
        return None
    try:
        return date.fromisoformat(v[:10])
    except ValueError:
        return None


def _dt(v: Any) -> datetime | None:
    if not v or not isinstance(v, str):
        return None
    try:
        return datetime.fromisoformat(v.replace("Z", "+00:00").replace("+0000", "+00:00"))
    except ValueError:
        return None


def _quote(key: str) -> str:
    return key.replace("\\", "\\\\").replace('"', '\\"')


class JiraConnector:
    def __init__(self, client: ReadOnlyHttpClient, *, flavor: str, base_url: str, fields: fm.JiraFields,
                 aspirations: list[str]) -> None:
        self.source_id = "jira"
        self.client = client
        self.cloud = flavor == "cloud"
        self.api = "/rest/api/3" if self.cloud else "/rest/api/2"
        self.base_url = base_url.rstrip("/")
        self.f = fields
        self.aspirations = aspirations

    # -- search ------------------------------------------------------------------

    def _jql(self, template: str, key: str | None = None) -> str:
        return template.replace("{key}", _quote(key)) if key is not None else template

    async def search(self, jql: str, fields: list[str], limit: int | None = None) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        if self.cloud:
            token = None
            for _ in range(MAX_PAGES):
                params: dict[str, Any] = {"jql": jql, "fields": ",".join(fields) or "id", "maxResults": PAGE}
                if token:
                    params["nextPageToken"] = token
                page = await self.client.get_json(f"{self.api}/search/jql", params)
                out += page.get("issues", [])
                token = page.get("nextPageToken")
                if not token or page.get("isLast") or (limit and len(out) >= limit):
                    break
        else:
            start = 0
            for _ in range(MAX_PAGES):
                page = await self.client.get_json(f"{self.api}/search", {
                    "jql": jql, "fields": ",".join(fields) or "id", "startAt": start, "maxResults": PAGE})
                issues = page.get("issues", [])
                out += issues
                start += len(issues)
                if not issues or start >= page.get("total", 0) or (limit and len(out) >= limit):
                    break
        return out[:limit] if limit else out

    async def count(self, jql: str) -> int:
        if not self.cloud:
            return int((await self.client.get_json(f"{self.api}/search", {"jql": jql, "maxResults": 0}))["total"])
        # Cloud has no GET count, so page through ids only.
        n, token = 0, None
        for _ in range(MAX_PAGES):
            params: dict[str, Any] = {"jql": jql, "fields": "id", "maxResults": 5000}
            if token:
                params["nextPageToken"] = token
            page = await self.client.get_json(f"{self.api}/search/jql", params)
            n += len(page.get("issues", []))
            token = page.get("nextPageToken")
            if not token or page.get("isLast"):
                return n
        raise SourceUnavailable(f"JIRA: more than {MAX_PAGES} pages for one count")

    # -- projects ----------------------------------------------------------------

    def _ref(self, p: dict[str, Any]) -> ProjectRef:
        updated = _dt((p.get("insight") or {}).get("lastIssueUpdateTime"))
        return ProjectRef(key=p["key"], name=p["name"], url=f"{self.base_url}/browse/{p['key']}", updated_at=updated)

    async def list_projects(self) -> list[ProjectRef]:
        if not self.cloud:
            return [self._ref(p) for p in await self.client.get_json(f"{self.api}/project", {"expand": "lead"})]
        out, start = [], 0
        for _ in range(MAX_PAGES):
            page = await self.client.get_json(f"{self.api}/project/search",
                                              {"startAt": start, "maxResults": 50, "expand": "lead,insight"})
            values = page.get("values", [])
            out += [self._ref(p) for p in values]
            start += len(values)
            if page.get("isLast", True) or not values:
                return out
        return out

    async def _anchor(self, key: str, extra: list[str]) -> dict[str, Any] | None:
        if not self.f.anchor_jql:
            return None
        found = await self.search(self._jql(self.f.anchor_jql, key), ["status", "assignee", *extra], limit=1)
        return found[0]["fields"] if found else None

    async def get_project(self, key: str) -> SourceProject:
        p = await self.client.get_json(f"{self.api}/project/{quote(key, safe='')}", {"expand": "lead,insight"})
        wanted = [x for x in (self.f.start_date_field, self.f.end_date_field, self.f.strategy_field,
                              "" if self.f.percent_done == "tasks" else self.f.percent_done) if x]
        anchor = await self._anchor(key, wanted)
        if self.f.status_from == "anchor":
            if anchor is None:
                raise SourceUnavailable(f"JIRA: no anchor issue for {key} (field mapping → anchor JQL)")
            status = (anchor.get("status") or {}).get("name")
        else:
            status = (p.get("projectCategory") or {}).get("name")
        if not status:
            raise SourceUnavailable(f"JIRA: {key} has no status where the field mapping says to look")
        if self.f.owner_from == "lead":
            owner = (p.get("lead") or {}).get("displayName")
        else:
            owner = ((anchor or {}).get("assignee") or {}).get("displayName")
        a = anchor or {}
        if self.f.percent_done == "tasks":
            counts = await self.get_task_counts(key)
            percent = round(100 * counts.done / counts.total) if counts.total else None
        else:
            v = a.get(self.f.percent_done)
            percent = max(0, min(100, round(float(v)))) if isinstance(v, int | float) else None
        return SourceProject(
            **self._ref(p).model_dump(), owner=owner, team=(p.get("projectCategory") or {}).get("name"), status=status,
            start_date=_date(a.get(self.f.start_date_field)) if self.f.start_date_field else None,
            end_date=_date(a.get(self.f.end_date_field)) if self.f.end_date_field else None,
            percent_done=percent,
            strategy_tag=fm.aspiration(a.get(self.f.strategy_field), self.aspirations) if self.f.strategy_field else None,
        )

    async def get_milestones(self, key: str) -> list[SourceMilestone]:
        versions = await self.client.get_json(f"{self.api}/project/{quote(key, safe='')}/versions")
        return [SourceMilestone(name=v["name"], due_date=_date(v.get("releaseDate")),
                                status="done" if v.get("released") else "open")
                for v in versions if not v.get("archived")]

    async def get_sprints(self, key: str) -> list[SourceSprint]:
        boards = await self.client.get_json("/rest/agile/1.0/board", {"projectKeyOrId": key, "type": "scrum"})
        out: list[SourceSprint] = []
        seen: set[int] = set()
        for b in boards.get("values", []):
            start = 0
            for _ in range(MAX_PAGES):
                page = await self.client.get_json(f"/rest/agile/1.0/board/{b['id']}/sprint",
                                                  {"state": "active,future", "startAt": start, "maxResults": 50})
                values = page.get("values", [])
                for s in values:
                    if s["id"] in seen:
                        continue
                    seen.add(s["id"])
                    out.append(SourceSprint(name=s["name"], goal=s.get("goal") or None, start_date=_date(s.get("startDate")),
                                            end_date=_date(s.get("endDate")), state=s.get("state", "active")))
                start += len(values)
                if page.get("isLast", True) or not values:
                    break
        return out

    async def get_task_counts(self, key: str) -> TaskCounts:
        base = self._jql(self.f.task_jql, key)
        todo = await self.count(f'({base}) AND statusCategory = "To Do"')
        doing = await self.count(f'({base}) AND statusCategory = "In Progress"')
        done = await self.count(f'({base}) AND statusCategory = Done')
        return TaskCounts(todo=todo, in_progress=doing, done=done, total=todo + doing + done)

    async def get_links(self) -> list[SourceLink]:
        issues = await self.search(self.f.links_jql, ["issuelinks", "project"])
        seen: set[tuple[str, str]] = set()
        for i in issues:
            src = i["key"].rsplit("-", 1)[0]
            for link in (i.get("fields") or {}).get("issuelinks", []):
                t = link.get("type") or {}
                if (t.get("name") or "").lower() != "blocks":
                    continue
                if "outwardIssue" in link:  # this issue blocks the other one
                    pair = (src, link["outwardIssue"]["key"].rsplit("-", 1)[0])
                elif "inwardIssue" in link:  # the other one blocks this issue
                    pair = (link["inwardIssue"]["key"].rsplit("-", 1)[0], src)
                else:
                    continue
                if pair[0] != pair[1]:
                    seen.add(pair)
        return [SourceLink(from_key=a, to_key=b) for a, b in sorted(seen)]

    async def get_risks(self, key: str | None = None) -> list[SourceRisk]:
        if not (self.f.likelihood_field and self.f.impact_field and self.f.risk_jql):
            return []
        jql = f'project = "{_quote(key)}" AND ({self.f.risk_jql})' if key else self.f.risk_jql
        issues = await self.search(jql, ["summary", "assignee", self.f.likelihood_field, self.f.impact_field])
        out = []
        for i in issues:
            f = i.get("fields") or {}
            lk, im = fm.level(f.get(self.f.likelihood_field)), fm.level(f.get(self.f.impact_field))
            if lk is None or im is None:
                continue  # unknown level: not guessed
            out.append(SourceRisk(project_key=i["key"].rsplit("-", 1)[0], title=f.get("summary") or i["key"],
                                  likelihood=lk, impact=im, owner=(f.get("assignee") or {}).get("displayName")))
        return out
