"""Mock connector: serves design/sample-data.json as if it came from the real
tracker. Used until real API access exists, and in tests.

The sample file has no milestone lists, sprints or task counts. The
mock fills them in a fixed, clearly fake way:
- milestones: the one "next milestone" per project
- sprints: one active two-week sprint ending on the sample's as-of date
- task counts: 40 tasks, done = percent_done
- owners: as in the sample (placeholder names; Agent Ops Console has none)
A source whose sample status is "failed" raises SourceUnavailable on every call,
like the expired Multica token in the designs.
"""

import json
import re
from datetime import date, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any

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

MOCK_TASKS_PER_PROJECT = 40


@lru_cache
def load_sample(path: Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text())


def _slug(name: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "-", name.upper()).strip("-")


class MockConnector:
    def __init__(self, source_id: str, sample_path: Path, *, force_up: bool = False) -> None:
        self.source_id = source_id
        self.force_up = force_up  # ignore the sample's failure (demo history)
        self._data = load_sample(sample_path)
        self._source = next((s for s in self._data["sources"] if s["id"] == source_id), None)
        if self._source is None:
            raise ValueError(f"No source {source_id!r} in sample data")
        self._as_of = datetime.fromisoformat(self._data["as_of"])
        self._projects = {p["code"]: p for p in self._data["projects"] if p["source"] == source_id}
        self._non_compliant = [n for n in self._data.get("non_compliant", []) if n["source"] == source_id]

    def _check_up(self) -> None:
        if self._source.get("status") == "failed" and not self.force_up:
            raise SourceUnavailable(f"{self._source['name']}: {self._source.get('error', 'unavailable')}")

    def _url(self, key: str) -> str:
        return f"https://{self.source_id}.example.invalid/projects/{key}"

    def _get(self, key: str) -> dict[str, Any]:
        self._check_up()
        p = self._projects.get(key)
        if p is None:
            raise SourceUnavailable(f"{self._source['name']}: no project {key}")
        return p

    async def list_projects(self) -> list[ProjectRef]:
        self._check_up()
        refs = [
            ProjectRef(key=code, name=f"{code} {p['name']}", url=self._url(code),
                       updated_at=datetime.fromisoformat(p["source_updated_at"]))
            for code, p in self._projects.items()
        ]
        refs += [ProjectRef(key=_slug(n["name"]), name=n["name"], url=self._url(_slug(n["name"])))
                 for n in self._non_compliant]
        return refs

    async def get_project(self, key: str) -> SourceProject:
        p = self._get(key)
        return SourceProject(
            key=key, name=f"{key} {p['name']}", url=self._url(key),
            updated_at=datetime.fromisoformat(p["source_updated_at"]),
            owner=p.get("owner"), team=p.get("team"), status=p["status"],
            start_date=date.fromisoformat(p["start_date"]) if p.get("start_date") else None,
            end_date=date.fromisoformat(p["end_date"]) if p.get("end_date") else None,
            percent_done=p.get("percent_done"), strategy_tag=p.get("strategy_tag"),
        )

    async def get_milestones(self, key: str) -> list[SourceMilestone]:
        p = self._get(key)
        if not p.get("next_milestone"):
            return []
        done = p["status"] == "Done"
        return [SourceMilestone(
            name=p["next_milestone"],
            due_date=date.fromisoformat(p["next_milestone_due"]) if p.get("next_milestone_due") else None,
            status="done" if done else "open",
        )]

    async def get_sprints(self, key: str) -> list[SourceSprint]:
        p = self._get(key)
        if p["status"] in ("Done", "Not started"):
            return []
        end = self._as_of.date()
        return [SourceSprint(name=f"{key} sprint", goal=f"Work towards: {p.get('next_milestone') or 'next release'}",
                             start_date=end - timedelta(days=13), end_date=end, state="active")]

    async def get_task_counts(self, key: str) -> TaskCounts:
        p = self._get(key)
        total = MOCK_TASKS_PER_PROJECT
        done = round((p.get("percent_done") or 0) / 100 * total)
        in_progress = min(6, total - done)
        return TaskCounts(todo=total - done - in_progress, in_progress=in_progress, done=done, total=total)

    async def get_links(self) -> list[SourceLink]:
        self._check_up()
        return [SourceLink(from_key=d["from"], to_key=d["to"], kind=d.get("kind", "blocks"))
                for d in self._data.get("dependencies", []) if d["from"] in self._projects]

    async def get_risks(self, key: str | None = None) -> list[SourceRisk]:
        self._check_up()
        out = []
        for r in self._data.get("risks", []):
            if r["project"] not in self._projects or (key and r["project"] != key):
                continue
            out.append(SourceRisk(project_key=r["project"], title=r["title"],
                                  likelihood=r["likelihood"], impact=r["impact"]))
        return out
