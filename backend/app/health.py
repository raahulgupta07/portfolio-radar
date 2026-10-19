"""Health rule (PRD FR-17). Plain code, no LLM. Every result carries its reasons,
so Radar and the screens can show why a project has its colour.

- Done:      source status is Done.
- Off track: a milestone overdue by more than N days (default 3), or status
             On hold with any overdue milestone.
- At risk:   progress more than N points behind the share of time used
             (default 15); or next milestone within N days (default 7) while
             behind; or waits for an Off-track project; or no owner; or no
             milestone dates.
- On track:  everything else.
"""

from dataclasses import dataclass, field
from datetime import date
from zoneinfo import ZoneInfo

from app.settings import Settings

ON_TRACK, AT_RISK, OFF_TRACK, DONE = "on_track", "at_risk", "off_track", "done"
LABELS = {ON_TRACK: "On track", AT_RISK: "At risk", OFF_TRACK: "Off track", DONE: "Done"}


@dataclass(frozen=True)
class Thresholds:
    overdue_days: int = 3
    behind_points: int = 15
    milestone_window_days: int = 7

    @classmethod
    def from_settings(cls, s: Settings) -> "Thresholds":
        return cls(s.health_overdue_days, s.health_behind_points, s.health_milestone_window_days)


@dataclass(frozen=True)
class MilestoneInfo:
    name: str
    due_date: date | None
    done: bool


@dataclass(frozen=True)
class ProjectInfo:
    code: str
    status: str
    start_date: date | None
    end_date: date | None
    percent_done: int | None
    owner: str | None
    milestones: tuple[MilestoneInfo, ...] = ()
    waits_for: tuple[str, ...] = ()  # codes of projects that block this one


@dataclass
class HealthResult:
    health: str
    reasons: list[str] = field(default_factory=list)
    time_used_pct: float | None = None
    behind_points: float | None = None


def today_in(settings: Settings) -> date:
    if settings.today:
        return date.fromisoformat(settings.today)
    from datetime import datetime
    return datetime.now(ZoneInfo(settings.timezone)).date()


def time_used_pct(start: date | None, end: date | None, today: date) -> float | None:
    if not start or not end or end <= start:
        return None
    share = (today - start).days / (end - start).days
    return max(0.0, min(1.0, share)) * 100


def assess(p: ProjectInfo, today: date, t: Thresholds, off_track_codes: frozenset[str] = frozenset()) -> HealthResult:
    used = time_used_pct(p.start_date, p.end_date, today)
    behind = None if used is None or p.percent_done is None else round(used - p.percent_done, 1)

    if p.status == "Done":
        return HealthResult(DONE, ["Status is Done in the source"], used, behind)

    open_ms = [m for m in p.milestones if not m.done]
    overdue = [(m, (today - m.due_date).days) for m in open_ms if m.due_date and m.due_date < today]
    off = []
    for m, days in overdue:
        if days > t.overdue_days:
            off.append(f"Milestone '{m.name}' is {days} days overdue (due {m.due_date:%d %b})")
    if p.status == "On hold" and overdue and not off:
        m, days = overdue[0]
        off.append(f"On hold with milestone '{m.name}' overdue (due {m.due_date:%d %b})")
    elif p.status == "On hold" and off:
        off.append("Status is On hold")
    if off:
        return HealthResult(OFF_TRACK, off, used, behind)

    risk = []
    if behind is not None and behind > t.behind_points:
        risk.append(f"Progress {p.percent_done}% is {behind:g} points behind time used ({used:.0f}%)")
    upcoming = sorted((m for m in open_ms if m.due_date and m.due_date >= today), key=lambda m: m.due_date)
    if upcoming and behind is not None and behind > 0:
        nxt = upcoming[0]
        days = (nxt.due_date - today).days
        if days <= t.milestone_window_days:
            risk.append(f"Next milestone '{nxt.name}' is due in {days} days and the project is behind")
    blockers = sorted(set(p.waits_for) & off_track_codes)
    if blockers:
        risk.append("Waits for Off-track project " + ", ".join(blockers))
    if not p.owner:
        risk.append("No owner")
    if not p.milestones or any(m.due_date is None for m in open_ms):
        risk.append("No milestone dates")
    if risk:
        return HealthResult(AT_RISK, risk, used, behind)
    return HealthResult(ON_TRACK, [], used, behind)


def assess_all(projects: list[ProjectInfo], today: date, t: Thresholds) -> dict[str, HealthResult]:
    """Two passes: Off track first, so 'waits for an Off-track project' can use it."""
    first = {p.code: assess(p, today, t) for p in projects}
    off = frozenset(code for code, r in first.items() if r.health == OFF_TRACK)
    return {p.code: assess(p, today, t, off) for p in projects}
