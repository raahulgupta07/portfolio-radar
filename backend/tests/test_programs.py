"""Program office view: KPIs, charter completeness, budget totals and the import."""

import json
from datetime import date

from app.db import session_scope
from app.portfolio import programs

TODAY = date(2026, 10, 20)


def _p(status="In Progress", target="", a="", **kw):
    return programs.project_row({"id": "X", "name": "x", "program": "p", "status": status, "target": target,
                                 "raci": {"A": a}, **kw}, TODAY)


def test_kpis_count_open_work_only():
    rows = [
        _p("Completed", target="2026-01-01", a="Ann"),   # closed: never past target
        _p("In Progress", target="2026-10-25", a="Ann"),  # due in 5 days
        _p("Planned", target="2026-10-01", a="Ann, Bob"),  # past target, two accountable
        _p("Pending Approval"),                           # no accountable
    ]
    k = programs.kpis(rows)
    assert (k["projects"], k["completed"], k["active"], k["pending_approval"], k["planned"]) == (4, 1, 1, 1, 1)
    assert (k["due_30"], k["past_target"], k["no_accountable"]) == (1, 1, 2)


def test_charter_completeness_and_budget_totals():
    pr = {"pm": "A", "sponsor": "B", "start": "2026-01-01", "end": "2026-12-31", "goal": "g",
          "budget": [{"prudent": "100", "expansionary": "150", "actual": ""}, {"prudent": 50, "actual": 20}]}
    done = {c["label"] for c in programs.charter_checks(pr) if c["done"]}
    assert done == {"Program manager", "Sponsor", "Start and end dates", "Goal", "Budget"}
    assert programs.budget_totals(pr) == {"prudent": 150.0, "expansionary": 150.0, "actual": 20.0}
    assert programs.budget_totals({}) == {"prudent": None, "expansionary": None, "actual": None}


async def test_import_then_view(tmp_path):
    doc = {"programs": {"b2b": {"id": "b2b", "name": "B2B", "order": 1, "pm": "Ann", "milestones": [{"id": "m1", "name": "Go live"}]}},
           "activity": {"a1": {"at": "2026-10-10T05:35:45Z", "by": "Ann", "kind": "project", "projectId": "P-1", "projectName": "Portal", "type": "updated", "changes": [{"field": "status", "from": "Planned", "to": "In Progress"}]}},
           "projects": {"P-1": {"id": "P-1", "name": "Portal", "program": "b2b", "status": "Planned", "milestoneId": "m1",
                                "raci": {"R": "Bo", "A": "Ann", "C": "", "I": ""}}}}
    f = tmp_path / "po.json"
    f.write_text(json.dumps(doc))
    async with session_scope() as s:
        assert await programs.import_file(s, f) == {"programs": 1, "projects": 1, "activity": 1}
    async with session_scope() as s:
        v = await programs.programs_view(s, TODAY)
    assert v["programs"][0]["name"] == "B2B" and v["programs"][0]["kpis"]["projects"] == 1
    assert v["activity"][0]["changes"][0]["to"] == "In Progress" and v["today"] == "2026-10-20"
    assert v["projects"][0]["raci"]["A"] == "Ann" and v["projects"][0]["milestone"] == "Go live"
    async with session_scope() as s:  # a second import replaces, never duplicates
        await programs.import_file(s, f)
        assert (await programs.programs_view(s, TODAY))["kpis"]["projects"] == 1
