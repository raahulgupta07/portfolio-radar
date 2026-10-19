"""Radar's checks (docs/radar-agent.md → "Checks"). Plain code, no LLM.

Input is what /portfolio returns (project rows and sources). Output is a list
of findings, each with a stable `key` so Radar can say "seen for 3 days" and
does not raise the same alert twice.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}


@dataclass
class FindingDraft:
    key: str
    type: str  # health, stale, data, slipping, sync, change
    severity: str  # high, medium, low
    text: str
    detail: str
    project_code: str | None
    evidence: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _d(v: str | None) -> date | None:
    return date.fromisoformat(v[:10]) if v else None


def _days(n: int) -> str:
    return f"{n} day{'s' if n != 1 else ''}"


def check(projects: list[dict[str, Any]], sources: list[dict[str, Any]], today: date,
          stale_days: int = 14, timezone: str = "Asia/Yangon") -> list[FindingDraft]:
    out: list[FindingDraft] = []
    src_by_id = {s["id"]: s for s in sources}

    # Sync: a source that failed keeps its last good data; say how old it is.
    for s in sources:
        if s.get("stale"):
            last_good = s.get("last_good_sync_at")
            age = ((today - datetime.fromisoformat(last_good).astimezone(ZoneInfo(timezone)).date()).days
                   if last_good else None)
            out.append(FindingDraft(
                key=f"sync:{s['id']}", type="sync", severity="medium",
                text=f"{s['name']} data is {_days(age)} old" if age is not None else f"{s['name']} has never synced",
                detail=f"Sync failed: {s.get('error') or 'unknown error'}. {s.get('projects', 0)} projects show their last good data.",
                project_code=None,
                evidence={"source": s["id"], "error": s.get("error"), "last_good_sync_at": last_good,
                          "rule": "source sync failed"}))

    for p in projects:
        if p.get("health") == "done":
            continue
        code, short = p["code"], p["short"]
        ev = {"source": p["source"], "project": code, "synced_at": p.get("synced_at"),
              "stale": p.get("stale", False)}
        due = _d(p.get("next_milestone_due"))
        pct = p.get("percent_done")

        if p.get("health") == "off_track":
            if due and due < today:
                text = f"{short} milestone {_days((today - due).days)} overdue"
            else:
                text = f"{short} is off track"
            blocks = p.get("blocks") or []
            detail = "; ".join(p.get("health_reasons") or []) + (f". Blocks {', '.join(blocks)}." if blocks else ".")
            out.append(FindingDraft(f"health:{code}", "health", "high", text, detail, code,
                                    {**ev, "rule": "off track", "reasons": p.get("health_reasons")}))
        elif p.get("health") == "at_risk":
            reasons = [r for r in (p.get("health_reasons") or []) if r not in ("No owner", "No milestone dates")]
            if reasons:
                if due and due >= today and pct is not None:
                    text = f"{short} slipping: {p['next_milestone'].lower()} in {_days((due - today).days)}, {pct}% done"
                else:
                    text = f"{short} at risk"
                out.append(FindingDraft(f"slipping:{code}", "slipping", "medium", text, "; ".join(reasons) + ".", code,
                                        {**ev, "rule": "at risk", "reasons": reasons}))

        # Data quality
        if not p.get("owner"):
            out.append(FindingDraft(f"data:owner:{code}", "data", "low", f"{short} has no owner",
                                    f"Set an owner for {p['name']} in {p['source_name']}.", code,
                                    {**ev, "rule": "no owner", "field": "owner"}))
        if p.get("milestones", 0) == 0 or p.get("milestones_without_date", 0) > 0:
            out.append(FindingDraft(f"data:dates:{code}", "data", "low", f"{short} has no milestone dates",
                                    f"Add milestone dates for {p['name']} in {p['source_name']}.", code,
                                    {**ev, "rule": "no milestone dates", "field": "milestones"}))
        if p.get("active_sprint") and not p.get("sprint_goal"):
            out.append(FindingDraft(f"data:goal:{code}", "data", "low", f"{short} sprint has no goal",
                                    f"{p['active_sprint']} has no sprint goal in {p['source_name']}.", code,
                                    {**ev, "rule": "no sprint goal", "field": "sprint goal"}))

        # Stale work: no change in the source for N days (not the same as a failed sync).
        updated = _d(p.get("updated"))
        if updated and (today - updated).days >= stale_days and not src_by_id.get(p["source"], {}).get("stale"):
            out.append(FindingDraft(f"stale:{code}", "stale", "medium",
                                    f"{short} has no update for {_days((today - updated).days)}",
                                    f"Nothing changed in {p['source_name']} since {updated:%d %b}.", code,
                                    {**ev, "rule": f"no update for {stale_days} days", "updated": p.get("updated")}))

        # Change: got worse since last week.
        before, now = p.get("health_last_week"), p.get("health")
        rank = {"on_track": 0, "at_risk": 1, "off_track": 2}
        if before in rank and now in rank and rank[now] > rank[before]:
            label = {"at_risk": "At risk", "off_track": "Off track"}[now]
            out.append(FindingDraft(f"change:{code}:{now}", "change", "low", f"{short} turned {label} this week",
                                    f"Was {before.replace('_', ' ')} a week ago.", code,
                                    {**ev, "rule": "health got worse", "from": before, "to": now}))

    out.sort(key=lambda f: (SEVERITY_ORDER[f.severity], f.type != "health", f.key))
    return out
