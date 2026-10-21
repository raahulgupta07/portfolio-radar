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


# -- Admin edits -------------------------------------------------------------------------------

import pytest  # noqa: E402
from sqlalchemy import delete, select  # noqa: E402

from app.mcp.servers import portfolio  # noqa: E402
from app.models.app import PoActivity, PoProgram, PoProject  # noqa: E402


@pytest.fixture
async def empty_po():
    async with session_scope() as s:
        for m in (PoActivity, PoProject, PoProgram):
            await s.execute(delete(m))
    yield


async def _program(name="Digital Core", **kw):
    async with session_scope() as s:
        return (await programs.save_program(s, {"name": name, **kw}, "Rahul"))["id"]


async def _project(program, **kw):
    async with session_scope() as s:
        return await programs.save_project(s, {"program": program, "name": "Portal", **kw}, "Rahul")


async def _activity():
    async with session_scope() as s:
        return (await s.execute(select(PoActivity).order_by(PoActivity.at, PoActivity.id))).scalars().all()


async def test_add_edit_delete_a_project_and_log_each_step(empty_po):
    prog = await _program()
    assert prog == "digital-core"
    first = await _project(prog, status="Planned", raci={"A": "Ann"})
    second = await _project(prog, name="Second")
    assert (first["id"], second["id"]) == ("DIG-001", "DIG-002")

    async with session_scope() as s:
        r = await programs.save_project(s, {"id": "DIG-001", "program": prog, "name": "Portal", "status": "In Progress",
                                            "pct": 40, "raci": {"A": "Ann", "R": "Bo"}}, "Rahul (local:superadmin)")
    assert r["changes"] == 3  # status, pct and raci.R
    async with session_scope() as s:
        row = await s.get(PoProject, "DIG-001")
        assert row.data["status"] == "In Progress" and row.data["updatedBy"] == "Rahul (local:superadmin)"
        assert row.data["createdAt"] and row.data["pct"] == 40

    async with session_scope() as s:  # saving the same values again changes nothing and logs nothing
        before = len(await _activity())
        again = await programs.save_project(s, {"id": "DIG-001", "program": prog, "name": "Portal", "status": "In Progress",
                                                "pct": 40, "raci": {"A": "Ann", "R": "Bo"}}, "Rahul")
        assert again["changes"] == 0
    assert len(await _activity()) == before

    async with session_scope() as s:
        await programs.delete_project(s, "DIG-002", "Rahul")
    kinds = [(a.type, a.ref_id) for a in await _activity()]
    assert kinds.count(("created", "DIG-001")) == 1 and ("deleted", "DIG-002") in kinds and ("updated", "DIG-001") in kinds
    async with session_scope() as s:
        assert await s.get(PoProject, "DIG-002") is None
        v = await programs.programs_view(s, TODAY)
    assert v["kpis"]["projects"] == 1


async def test_edit_history_names_the_fields_and_hides_long_text(empty_po):
    prog = await _program()
    await _project(prog, remarks="short")
    async with session_scope() as s:
        await programs.save_project(s, {"id": "DIG-001", "program": prog, "name": "Portal", "remarks": "x" * 500}, "Rahul")
    last = [a for a in await _activity() if a.type == "updated"][-1]
    assert last.changes == [{"field": "remarks", "from": "", "to": "(text updated)"}]


async def test_an_edit_that_leaves_a_field_out_keeps_it(empty_po):
    prog = await _program(pm="Aye Thu", team=[{"name": "Bo", "role": "Lead"}])
    await _project(prog, owner="Ann", nextStep="Book the pilot", raci={"A": "Ann"})
    async with session_scope() as s:
        await programs.save_project(s, {"id": "DIG-001", "program": prog, "status": "On Hold"}, "Rahul")
        await programs.save_program(s, {"id": prog, "statusSummary": "Slipped a week"}, "Rahul")
    async with session_scope() as s:
        p = (await s.get(PoProject, "DIG-001")).data
        c = (await s.get(PoProgram, prog)).data
    assert (p["status"], p["name"], p["owner"], p["nextStep"], p["raci"]["A"]) == ("On Hold", "Portal", "Ann", "Book the pilot", "Ann")
    assert (c["statusSummary"], c["pm"], c["team"][0]["name"]) == ("Slipped a week", "Aye Thu", "Bo")


@pytest.mark.parametrize("patch,message", [
    ({"name": " "}, "needs a name"),
    ({"status": "Done"}, "Status must be one of"),
    ({"pct": 101}, "between 0 and 100"),
    ({"pct": "ten"}, "whole number"),
    ({"health": "Purple"}, "Green, Amber or Red"),
    ({"targetPrecision": "week"}, "day or month"),
    ({"start": "31/10/2026"}, "written like 2026-10-31"),
    ({"start": "2026-10-31", "target": "2026-01-01"}, "before the start date"),
    ({"name": "n" * 201}, "longer than 200"),
])
async def test_a_bad_project_is_refused_and_nothing_is_saved(empty_po, patch, message):
    prog = await _program()
    with pytest.raises(programs.SaveError, match=message):
        await _project(prog, **patch)
    async with session_scope() as s:
        assert (await s.execute(select(PoProject))).scalars().all() == []
    assert [a for a in await _activity() if a.kind == "project"] == []


async def test_a_project_needs_a_real_program_and_a_known_id(empty_po):
    with pytest.raises(programs.SaveError, match="Pick a program"):
        await _project("nope")
    prog = await _program()
    async with session_scope() as s:
        with pytest.raises(programs.SaveError, match="no project DIG-9"):
            await programs.save_project(s, {"id": "DIG-9", "program": prog, "name": "x"}, "Rahul")
        with pytest.raises(programs.SaveError, match="Say who"):
            await programs.save_project(s, {"program": prog, "name": "x"}, "  ")
        with pytest.raises(programs.SaveError, match="no project DIG-9"):
            await programs.delete_project(s, "DIG-9", "Rahul")


async def test_a_stale_editor_cannot_overwrite_a_newer_save(empty_po):
    prog = await _program()
    created = await _project(prog)
    opened_at = created["updated_at"]
    async with session_scope() as s:  # someone else saves first
        row = await s.get(PoProject, "DIG-001")
        row.data = {**row.data, "updatedAt": "2099-01-01T00:00:00Z"}
    async with session_scope() as s:
        with pytest.raises(programs.SaveError, match="Someone changed this project"):
            await programs.save_project(s, {"id": "DIG-001", "program": prog, "name": "Mine", "base_updated_at": opened_at}, "Rahul")
    async with session_scope() as s:
        assert (await s.get(PoProject, "DIG-001")).name == "Portal"


async def test_charter_edit_cleans_rows_and_drops_dead_milestone_links(empty_po):
    prog = await _program(milestones=[{"id": "m1", "name": "Pilot", "target": "2026-11-15"}, {"name": "Go live"}])
    async with session_scope() as s:
        data = (await s.get(PoProgram, prog)).data
    assert [m["name"] for m in data["milestones"]] == ["Pilot", "Go live"]
    assert data["milestones"][1]["id"].startswith("m-")  # a missing id is made up
    await _project(prog, milestoneId="m1")

    async with session_scope() as s:
        r = await programs.save_program(s, {"id": prog, "name": "Digital Core", "pm": "Aye Thu", "start": "2026-01-01",
                                            "end": "2026-12-31", "budget": [{"item": "Licences", "prudent": "100"}, {}],
                                            "milestones": [{"id": "m2", "name": "Rollout"}]}, "Rahul")
    assert r["changes"] >= 3
    async with session_scope() as s:
        v = await programs.programs_view(s, TODAY)
    p = v["programs"][0]
    assert p["pm"] == "Aye Thu" and p["budget_totals"]["prudent"] == 100.0 and len(p["budget"]) == 1  # the empty row is gone
    assert v["projects"][0]["milestone_id"] == ""  # its milestone no longer exists
    assert [a for a in v["activity"] if a["kind"] == "program" and a["type"] == "updated"]


@pytest.mark.parametrize("patch,message", [
    ({"name": ""}, "needs a name"),
    ({"name": "!!!"}, "letters or numbers"),
    ({"start": "2026-12-31", "end": "2026-01-01"}, "end date is before"),
    ({"milestones": [{"id": "a", "name": "x"}, {"id": "a", "name": "y"}]}, "share the id"),
    ({"milestones": [{"name": "x", "target": "soon"}]}, "written like"),
    ({"budget": "lots"}, "list of at most"),
    ({"team": [{"name": str(i)} for i in range(61)]}, "at most 60"),
])
async def test_a_bad_charter_is_refused(empty_po, patch, message):
    with pytest.raises(programs.SaveError, match=message):
        await _program(**patch)


async def test_programs_with_projects_cannot_be_deleted(empty_po):
    prog = await _program()
    with pytest.raises(programs.SaveError, match="exists already"):
        await _program()
    await _project(prog)
    async with session_scope() as s:
        with pytest.raises(programs.SaveError, match="still has 1 project"):
            await programs.delete_program(s, prog, "Rahul")
        await programs.delete_project(s, "DIG-001", "Rahul")
        await programs.delete_program(s, prog, "Rahul")
    async with session_scope() as s:
        assert await s.get(PoProgram, prog) is None
    assert ("program", "deleted") in [(a.kind, a.type) for a in await _activity()]


def test_only_admin_people_can_use_the_edit_tools():
    for name in ("save_project", "delete_project", "save_program", "delete_program"):
        spec = portfolio.server.tools[name]
        assert spec.callers == frozenset({"human"}) and spec.roles == frozenset({"admin"}) and not spec.read_only
    assert portfolio.server.tools["get_programs"].read_only  # reading stays read-only, for everyone who could read it
