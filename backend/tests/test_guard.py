"""The guard: off by default, caller kinds, roles, review of changed tools,
rate limit, argument checks, field projection, PII removal, audit."""

from pydantic import BaseModel
from sqlalchemy import select

from app.db import session_scope
from app.mcp.guard import Gateway
from app.mcp.registry import Registry, ServerDef
from app.models.mcp import McpCall, McpTool, McpToolChange
from tests.conftest import ADAPTER, ADMIN, RADAR, VIEWER, make_settings


class Echo(BaseModel):
    text: str
    times: int = 1


def make_server(description: str = "Repeat the text.") -> ServerDef:
    s = ServerDef(name="demo", title="Demo", description="Test server", owner="tests", direction="out")

    @s.tool(callers={"human", "agent"}, roles={"viewer", "agent"}, input_model=Echo, description=description)
    async def echo(args: Echo, ctx) -> dict:
        return {"text": args.text * args.times, "by": ctx.caller.id}

    @s.tool(callers={"human"}, roles={"approver"})
    async def approve_things(args, ctx) -> dict:
        """Only human approvers."""
        return {"ok": True}

    @s.tool(callers={"service"})
    async def contacts(args, ctx) -> list:
        """Returns personal data, to test removal."""
        return [
            {"name": "Aung Aung", "email": "aung@cityholdings.com.mm", "phone": "+95 9 450 123 456",
             "note": "call 09451234567 before 2026-10-19", "team": {"name": "Digital", "size": 12}},
            {"name": "Su Su", "email": "su@example.com", "phone": None, "note": "", "team": {"name": "Data", "size": 5}},
        ]

    @s.tool(callers={"agent"})
    async def broken(args, ctx) -> dict:
        """Always fails."""
        raise RuntimeError("secret internal detail")

    return s


async def setup(server: ServerDef | None = None, on: tuple[str, ...] = ("echo", "approve_things", "contacts", "broken"),
                **settings_overrides) -> Gateway:
    settings = make_settings(**settings_overrides)
    registry = Registry(settings)
    registry.add(server or make_server())
    async with session_scope() as session:
        await registry.sync(session)
        for name in on:
            await registry.set_status(session, "demo", name, "on", by="tests")
    return Gateway(registry, settings)


async def audit_rows() -> list[McpCall]:
    async with session_scope() as session:
        return list((await session.scalars(select(McpCall).order_by(McpCall.id))).all())


async def test_new_tools_start_off_and_are_blocked():
    gw = await setup(on=())
    async with session_scope() as session:
        statuses = {t.name: t.status for t in (await session.scalars(select(McpTool))).all()}
    assert set(statuses.values()) == {"off"}

    r = await gw.call(VIEWER, "demo", "echo", {"text": "hi"})
    assert r.outcome == "denied"
    assert "switched off" in r.message
    assert [(a.outcome, a.tool) for a in await audit_rows()] == [("denied", "echo")]


async def test_allowed_call_runs_and_is_audited():
    gw = await setup()
    r = await gw.call(VIEWER, "demo", "echo", {"text": "ab", "times": 2})
    assert r.outcome == "ok"
    assert r.value["text"] == "abab"
    rows = await audit_rows()
    assert rows[-1].outcome == "ok" and rows[-1].caller_kind == "human"


async def test_wrong_caller_kind_is_blocked():
    gw = await setup()
    r = await gw.call(ADAPTER, "demo", "echo", {"text": "x"})
    assert r.outcome == "denied"
    assert "Service callers may not use this tool" in r.message


async def test_agent_cannot_use_human_only_tool_even_with_roles():
    gw = await setup()
    r = await gw.call(RADAR, "demo", "approve_things", {})
    assert r.outcome == "denied"
    assert "Agent callers" in r.message


async def test_missing_role_is_blocked():
    gw = await setup()
    r = await gw.call(VIEWER, "demo", "approve_things", {})
    assert r.outcome == "denied"
    assert "Missing role" in r.message


async def test_unknown_tool_is_blocked_and_audited():
    gw = await setup()
    r = await gw.call(VIEWER, "demo", "drop_tables", {})
    assert r.outcome == "denied"
    assert (await audit_rows())[-1].tool == "drop_tables"


async def test_list_tools_shows_only_usable_tools_for_this_caller():
    gw = await setup(on=("echo", "approve_things"))
    assert [t.name for t in await gw.list_tools(VIEWER, "demo")] == ["echo"]
    assert [t.name for t in await gw.list_tools(RADAR, "demo")] == ["echo"]
    assert [t.name for t in await gw.list_tools(ADAPTER, "demo")] == []  # contacts is off


async def test_changed_tool_waits_for_review_until_owner_approves():
    gw = await setup()
    assert (await gw.call(VIEWER, "demo", "echo", {"text": "a"})).outcome == "ok"

    changed = make_server(description="Repeat the text, now also in capitals.")
    settings = make_settings()
    registry = Registry(settings)
    registry.add(changed)
    async with session_scope() as session:
        report = await registry.sync(session)
    assert report["review"] == ["demo.echo"]
    gw2 = Gateway(registry, settings)

    r = await gw2.call(VIEWER, "demo", "echo", {"text": "a"})
    assert r.outcome == "denied" and "waiting for its owner" in r.message

    async with session_scope() as session:
        change = await session.scalar(select(McpToolChange))
        assert change.status == "pending"
        assert change.diff["description"]["new"].endswith("capitals.")
        await registry.decide_change(session, change.id, approve=True, by="owner")
    assert (await gw2.call(VIEWER, "demo", "echo", {"text": "a"})).outcome == "ok"


async def test_a_tool_in_review_cannot_simply_be_turned_on():
    await setup()
    changed = make_server(description="Something else.")
    registry = Registry(make_settings())
    registry.add(changed)
    async with session_scope() as session:
        await registry.sync(session)
    async with session_scope() as session:
        try:
            await registry.set_status(session, "demo", "echo", "on", by="someone")
        except ValueError as e:
            assert "pending change" in str(e)
        else:
            raise AssertionError("expected ValueError")


async def test_rate_limit_per_caller():
    gw = await setup(rate_limit_per_minute=3)
    outcomes = [(await gw.call(VIEWER, "demo", "echo", {"text": "x"})).outcome for _ in range(4)]
    assert outcomes == ["ok", "ok", "ok", "denied"]
    assert (await gw.call(RADAR, "demo", "echo", {"text": "x"})).outcome == "ok"  # other caller unaffected


async def test_invalid_arguments_are_an_error_not_a_crash():
    gw = await setup()
    r = await gw.call(VIEWER, "demo", "echo", {"times": "many"})
    assert r.outcome == "error"
    assert "text" in r.message and "times" in r.message


async def test_tool_crash_hides_internal_detail():
    gw = await setup()
    r = await gw.call(RADAR, "demo", "broken", {})
    assert r.outcome == "error"
    assert "secret" not in r.message
    assert (await audit_rows())[-1].outcome == "error"


async def test_pii_is_removed_from_answers_and_audit():
    gw = await setup()
    await gw.call(VIEWER, "demo", "echo", {"text": "mail me at a@b.com or +95 9 450 123 456"})
    r = await gw.call(ADAPTER, "demo", "contacts", {})
    first = r.value[0]
    assert first["email"] == "[email removed]"
    assert first["phone"] == "[phone removed]"
    assert first["note"] == "call [phone removed] before 2026-10-19"  # the date stays
    assert first["name"] == "Aung Aung"
    echo_row = (await audit_rows())[0]
    assert "a@b.com" not in echo_row.args and "450 123 456" not in echo_row.args
    assert "[email removed]" in echo_row.args


async def test_fields_projection_trims_the_answer():
    gw = await setup()
    r = await gw.call(ADAPTER, "demo", "contacts", {"fields": ["name", "team.name"]})
    assert r.value == [{"name": "Aung Aung", "team": {"name": "Digital"}}, {"name": "Su Su", "team": {"name": "Data"}}]


async def test_admin_with_viewer_role_can_use_viewer_tools():
    gw = await setup()
    assert (await gw.call(ADMIN, "demo", "echo", {"text": "x"})).outcome == "ok"
