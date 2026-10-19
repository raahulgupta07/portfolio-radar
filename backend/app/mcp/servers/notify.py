"""`/notify/mcp`: what the Notifier may see and do. It only ever sees drafts a
person approved, and only records the result of sending them."""

from datetime import UTC, datetime, timedelta

from pydantic import BaseModel, Field
from sqlalchemy import select

from app.db import session_scope
from app.mcp.guard import ToolError
from app.mcp.registry import ServerDef, ToolContext
from app.models.app import Approval, RadarMessage

server = ServerDef(
    name="notify",
    title="Notify",
    description="Approved digests and nudges waiting to be sent. For the Notifier service only.",
    owner="PMO",
    direction="out",
)

CALLERS = {"service"}
ROLES = {"notifier"}


@server.tool(callers=CALLERS, roles=ROLES, redact=False)
async def list_ready(args, ctx: ToolContext) -> dict:
    """Approved drafts not sent yet whose send time has come."""
    now = datetime.now(UTC)
    async with session_scope() as session:
        rows = (await session.scalars(select(Approval).where(Approval.status == "approved",
                                                             Approval.sent_at.is_(None)).order_by(Approval.id))).all()
    ready = []
    for a in rows:
        try:
            send_at = datetime.fromisoformat(a.draft_json["send_at"]) if a.draft_json.get("send_at") else None
            if send_at is not None and send_at.tzinfo is None:
                send_at = send_at.replace(tzinfo=UTC)
        except (TypeError, ValueError):
            send_at = None  # a bad time must not stop every other draft; send as soon as approved
        if send_at and send_at > now:
            continue
        if (a.draft_json.get("send_result") or {}).get("attempts", 0) >= 5:
            continue
        ready.append({"id": a.id, "kind": a.kind, "title": a.draft_json.get("title"), "to": a.draft_json.get("to"),
                      "body": a.draft_json.get("body"), "project": a.draft_json.get("project"),
                      "approved_by": a.decided_by})
    return {"ready": ready}


class SentArgs(BaseModel):
    approval_id: int
    ok: bool
    channels: list[str] = Field(default_factory=list)
    detail: str = Field("", max_length=500)


@server.tool(callers=CALLERS, roles=ROLES, input_model=SentArgs, read_only=False, redact=False)
async def mark_sent(args: SentArgs, ctx: ToolContext) -> dict:
    """Record the result of sending an approved draft."""
    async with session_scope() as session:
        a = await session.get(Approval, args.approval_id)
        if a is None or a.status != "approved":
            raise ToolError("Only approved drafts can be sent")
        if a.sent_at is not None:
            raise ToolError("Already sent")
        prev = a.draft_json.get("send_result") or {}
        a.draft_json = {**a.draft_json, "send_result": {
            "ok": args.ok, "channels": args.channels, "detail": args.detail,
            "attempts": prev.get("attempts", 0) + 1, "at": datetime.now(UTC).isoformat()}}
        if args.ok:
            a.sent_at = datetime.now(UTC)
            session.add(RadarMessage(user_id="role:approver", kind="pill", mood="happy",
                                     body=f"Sent: {a.draft_json.get('title')} ({', '.join(args.channels)})",
                                     payload_json={"approval_id": a.id}))
    return {"approval_id": args.approval_id, "sent": args.ok}


@server.tool(callers=CALLERS, roles=ROLES, redact=False)
async def get_channels(args, ctx: ToolContext) -> dict:
    """Where messages go (set in Admin → Connections): Teams webhook and bot, SMTP settings, with secrets by name only,
    and the City tenant the Teams bot signs in to."""
    from app import integrations

    async with session_scope() as session:
        teams, _ = await integrations.load(session, "teams", ctx.settings)
        email, _ = await integrations.load(session, "email", ctx.settings)
        sso, _ = await integrations.load(session, "sso", ctx.settings)
    return {"teams": teams.model_dump(mode="json"), "email": email.model_dump(mode="json"), "tenant_id": sso.tenant_id}


# -- Teams chat: Radar's answers to questions asked in Teams ---------------------------------
# A reply goes back only to the 1:1 chat where that person asked, like the chat in the app.
# Digests and other messages to people still need a person's approval (list_ready above).

TEAMS_MAX_ATTEMPTS = 3


@server.tool(callers=CALLERS, roles=ROLES, redact=False)
async def teams_replies(args, ctx: ToolContext) -> dict:
    """Radar's answers to questions people asked in Teams that are not delivered yet, with where to send them."""
    since = datetime.now(UTC) - timedelta(days=2)
    async with session_scope() as session:
        questions = {q.id: q for q in (await session.scalars(select(RadarMessage).where(
            RadarMessage.kind == "me", RadarMessage.created_at >= since,
            RadarMessage.payload_json["origin"].as_string() == "teams"))).all()}
        if not questions:
            return {"replies": []}
        answers = (await session.scalars(select(RadarMessage).where(
            RadarMessage.reply_to.in_(list(questions)), RadarMessage.kind == "radar").order_by(RadarMessage.id))).all()
    out = []
    for a in answers:
        p = a.payload_json or {}
        if p.get("teams_sent_at") or p.get("teams_attempts", 0) >= TEAMS_MAX_ATTEMPTS:
            continue
        teams = questions[a.reply_to].payload_json["teams"]
        evidence = p.get("evidence")
        out.append({"message_id": a.id, "text": a.body + (f"\n\n_Evidence: {evidence}_" if evidence else ""),
                    "service_url": teams["service_url"], "conversation_id": teams["conversation_id"],
                    "reply_to_activity": teams.get("activity_id")})
    return {"replies": out}


class TeamsSent(BaseModel):
    message_id: int
    ok: bool
    detail: str = Field("", max_length=300)


@server.tool(callers=CALLERS, roles=ROLES, input_model=TeamsSent, read_only=False, redact=False)
async def mark_teams_sent(args: TeamsSent, ctx: ToolContext) -> dict:
    """Record whether an answer reached Teams. After three failures it is not tried again (it stays in the app)."""
    async with session_scope() as session:
        m = await session.get(RadarMessage, args.message_id)
        if m is None or m.kind != "radar" or m.reply_to is None:
            raise ToolError("No such answer")
        p = dict(m.payload_json or {})
        if p.get("teams_sent_at"):
            raise ToolError("Already delivered")
        p["teams_attempts"] = p.get("teams_attempts", 0) + 1
        if args.ok:
            p["teams_sent_at"] = datetime.now(UTC).isoformat()
        else:
            p["teams_error"] = args.detail
        m.payload_json = p
    return {"message_id": args.message_id, "delivered": args.ok}
