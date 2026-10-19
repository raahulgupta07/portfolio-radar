"""`/radar/mcp`: the conversation with Radar, its findings, drafts, approvals
and memory.

Who may do what:
- people (human) read their conversation, ask questions, answer Radar's
  questions, manage memory; only approvers decide on drafts
- the Radar agent (agent) and the nightly Radar job (service, role `radar`)
  post messages, save findings and create drafts. They can never approve or send.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy import select

from app import appsettings
from app.db import session_scope
from app.mcp.guard import ToolError
from app.mcp.registry import ServerDef, ToolContext
from app.models.app import AgentRun, Approval, Finding, Project, RadarMessage, RadarMemory, Source

server = ServerDef(
    name="radar",
    title="Radar",
    description="Conversation with Radar, findings, drafts waiting for approval, and Radar's memory.",
    owner="PMO",
    direction="out",
)

HUMAN = {"human"}
RADAR_WRITERS = {"agent", "service"}
RADAR_ROLES = {"agent", "radar"}


def audiences(caller) -> list[str]:
    return [caller.id, "*", *[f"role:{r}" for r in sorted(caller.roles)]]


def _msg(m: RadarMessage) -> dict[str, Any]:
    return {"id": m.id, "kind": m.kind, "body": m.body, "mood": m.mood, "payload": m.payload_json or {},
            "created_at": m.created_at.isoformat(), "state": m.state, "reply_to": m.reply_to,
            "audience": "you" if not (m.user_id == "*" or m.user_id.startswith("role:")) else m.user_id}


def _approval(a: Approval) -> dict[str, Any]:
    return {"id": a.id, "kind": a.kind, "status": a.status, "title": a.draft_json.get("title"),
            "to": a.draft_json.get("to"), "body": a.draft_json.get("body"), "project": a.draft_json.get("project"),
            "send_at": a.draft_json.get("send_at"), "created_by": a.created_by, "decided_by": a.decided_by,
            "decided_at": a.decided_at.isoformat() if a.decided_at else None,
            "sent_at": a.sent_at.isoformat() if a.sent_at else None,
            "send_result": a.draft_json.get("send_result")}


async def radar_status(session, settings, caller=None) -> dict[str, Any]:
    """Radar's mood and status line. Priority: scanning > asking > alert > offline > happy > ready."""
    now = datetime.now(UTC)
    running = await session.scalar(select(AgentRun).where(AgentRun.ended_at.is_(None),
                                                          AgentRun.started_at > now - timedelta(minutes=15)))
    last = await session.scalar(select(AgentRun).where(AgentRun.ended_at.is_not(None)).order_by(AgentRun.id.desc()))
    findings = (await session.scalars(select(Finding).where(Finding.run_id == last.id, Finding.dismissed_at.is_(None)))).all() if last else []
    failed = (await session.scalars(select(Source).where(Source.last_status == "failed"))).all()
    is_approver = caller is not None and "approver" in caller.roles
    open_asks = pending = 0
    if is_approver:
        asks = (await session.scalars(select(RadarMessage).where(RadarMessage.kind == "ask",
                                                                 RadarMessage.user_id.in_(audiences(caller))))).all()
        open_asks = sum(1 for a in asks if not (a.payload_json or {}).get("answer"))
        pending = len((await session.scalars(select(Approval).where(Approval.status == "pending"))).all())
    admin = await appsettings.load(session, settings)

    if running:
        mood, text = "scanning", f"Checking projects… started {running.started_at:%H:%M} UTC"
    elif open_asks or pending:
        mood, text = "asking", "Waiting for you"
    elif any(f.severity == "high" for f in findings):
        n = len(findings)
        mood, text = "alert", f"{n} thing{'s' if n != 1 else ''} need{'' if n != 1 else 's'} you"
    elif failed:
        mood, text = "offline", f"Can't reach {', '.join(s.name for s in failed)}"
    elif last and not findings:
        mood, text = "happy", "All done · nothing needs you"
    elif not admin.radar_on:
        mood, text = "resting", "Radar is off in Admin"
    else:
        mood, text = "ready", "Ready · read-only"
    projects = len((await session.scalars(select(Project.id))).all())
    return {
        "mood": mood, "status_text": text, "radar_on": admin.radar_on,
        "rules": {"sync_time": admin.sync_time, "stale_days": admin.stale_days, "digest_day": admin.digest_day, "digest_time": admin.digest_time,
                  "digest_recipients": admin.digest_recipients, "timezone": admin.timezone,
                  "approvers_group": admin.approvers_group},
        "last_run": {"started_at": last.started_at.isoformat(), "ended_at": last.ended_at.isoformat(),
                     "projects_checked": last.projects_checked, "findings": last.findings, "drafts": last.drafts} if last else None,
        "open_asks": open_asks, "pending_approvals": pending, "findings": len(findings),
        "projects": projects, "sources": len((await session.scalars(select(Source.id))).all()),
        "routines": [
            {"when": f"Daily · {admin.sync_time} + 10 min", "what": "Health check"},
            {"when": "Mon · 09:00", "what": "Stale work check"},
            {"when": f"{admin.digest_day} · {admin.digest_time}", "what": "SteerCo digest"},
            {"when": "On event", "what": "Sync fails, red"},
        ],
    }


# -- reading -------------------------------------------------------------------

class ConversationArgs(BaseModel):
    limit: int = Field(120, ge=1, le=500)


@server.tool(callers=HUMAN, input_model=ConversationArgs, redact=False)
async def get_conversation(args: ConversationArgs, ctx: ToolContext) -> dict:
    """Your conversation with Radar: messages, cards, questions and drafts waiting for you, and Radar's mood."""
    async with session_scope() as session:
        rows = (await session.scalars(select(RadarMessage).where(RadarMessage.user_id.in_(audiences(ctx.caller)))
                                      .order_by(RadarMessage.id.desc()).limit(args.limit))).all()
        approvals = {}
        if "approver" in ctx.caller.roles or "admin" in ctx.caller.roles:
            approvals = {a.id: _approval(a) for a in (await session.scalars(select(Approval))).all()}
        status = await radar_status(session, ctx.settings, ctx.caller)
        memory = (await session.scalars(select(RadarMemory).order_by(RadarMemory.id))).all()
    messages = [_msg(m) for m in reversed(rows)]
    for m in messages:
        if m["kind"] == "approval":
            m["approval"] = approvals.get(m["payload"].get("approval_id"))
    waiting = []
    if "approver" in ctx.caller.roles:
        for m in messages:
            if m["kind"] == "ask" and not m["payload"].get("answer"):
                waiting.append({"type": "ask", "message_id": m["id"], "label": f"Answer: {m['payload'].get('short') or m['body'][:50]}"})
            if m["kind"] == "approval" and m.get("approval") and m["approval"]["status"] == "pending":
                waiting.append({"type": "approval", "message_id": m["id"], "kind": m["approval"]["kind"],
                                "label": f"Approve: {m['approval']['title']}"})
    thinking = any(m["kind"] == "me" and m["state"] == "pending" for m in messages)
    return {"messages": messages, "waiting": waiting, "status": status, "thinking": thinking,
            "memory": [{"id": x.id, "text": x.text, "created_by": x.created_by} for x in memory]}


@server.tool(callers={"human", "agent", "service"})
async def get_status(args, ctx: ToolContext) -> dict:
    """Radar's mood, status line, last check, routines and counts."""
    async with session_scope() as session:
        return await radar_status(session, ctx.settings, ctx.caller if ctx.caller.kind == "human" else None)


class FindingsArgs(BaseModel):
    run_id: int | None = Field(None, description="A run id; empty = the latest run")


@server.tool(callers={"human", "agent", "service"}, roles={"viewer", "agent", "radar"}, input_model=FindingsArgs)
async def get_findings(args: FindingsArgs, ctx: ToolContext) -> dict:
    """Radar's findings from one check: type, severity, text, evidence and when first seen."""
    async with session_scope() as session:
        run = await session.get(AgentRun, args.run_id) if args.run_id else await session.scalar(
            select(AgentRun).where(AgentRun.ended_at.is_not(None)).order_by(AgentRun.id.desc()))
        if run is None:
            return {"run": None, "findings": []}
        rows = (await session.scalars(select(Finding).where(Finding.run_id == run.id).order_by(Finding.id))).all()
        codes = {p.id: p.code for p in (await session.scalars(select(Project))).all()}
    return {"run": {"id": run.id, "started_at": run.started_at.isoformat(),
                    "ended_at": run.ended_at.isoformat() if run.ended_at else None,
                    "projects_checked": run.projects_checked},
            "findings": [{"id": f.id, "type": f.type, "severity": f.severity, "text": f.text,
                          "project": codes.get(f.project_id), "evidence": f.evidence_json,
                          "first_seen_at": f.first_seen_at.isoformat(), "dismissed": f.dismissed_at is not None}
                         for f in rows]}


# -- people --------------------------------------------------------------------

class AskArgs(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


@server.tool(callers=HUMAN, input_model=AskArgs, read_only=False, redact=False)
async def ask_radar(args: AskArgs, ctx: ToolContext) -> dict:
    """Send Radar a message. Radar answers in your conversation, usually within seconds."""
    async with session_scope() as session:
        m = RadarMessage(user_id=ctx.caller.id, kind="me", body=args.text.strip(), state="pending", payload_json={})
        session.add(m)
        await session.flush()
        return {"message_id": m.id, "state": "pending"}


class TeamsAsk(BaseModel):
    user: str = Field(min_length=3, max_length=200, pattern=r"^[^@\s]+@[^@\s]+$",
                      description="The sender's City account (user principal name), from Teams")
    text: str = Field(min_length=1, max_length=2000)
    service_url: str = Field(max_length=300, description="Where Teams wants the reply")
    conversation_id: str = Field(max_length=300)
    activity_id: str = Field("", max_length=200)


@server.tool(callers={"service"}, roles={"teams"}, input_model=TeamsAsk, read_only=False, redact=False)
async def ask_from_teams(args: TeamsAsk, ctx: ToolContext) -> dict:
    """A person's message to Radar in a Teams 1:1 chat, passed on by the Teams bot after Microsoft's token was
    checked. It joins that person's conversation; the notifier sends Radar's answer back to the same chat."""
    from app.teams.botframework import BotAuthError, safe_service_url

    try:
        service_url = safe_service_url(args.service_url)
    except BotAuthError as e:
        raise ToolError(str(e)) from e
    async with session_scope() as session:
        m = RadarMessage(user_id=args.user, kind="me", body=args.text.strip(), state="pending", payload_json={
            "origin": "teams", "teams": {"service_url": service_url, "conversation_id": args.conversation_id,
                                         "activity_id": args.activity_id}})
        session.add(m)
        await session.flush()
        return {"message_id": m.id, "state": "pending"}


class AnswerArgs(BaseModel):
    message_id: int
    answer: Literal["yes", "no"]


@server.tool(callers=HUMAN, roles={"approver"}, input_model=AnswerArgs, read_only=False)
async def answer_ask(args: AnswerArgs, ctx: ToolContext) -> dict:
    """Answer one of Radar's questions (the yellow "Radar asks" cards). Approvers only."""
    async with session_scope() as session:
        m = await session.get(RadarMessage, args.message_id)
        if m is None or m.kind != "ask" or m.user_id not in audiences(ctx.caller):
            raise ToolError("No such question for you")
        if (m.payload_json or {}).get("answer"):
            raise ToolError(f"Already answered: {m.payload_json['answer']}")
        m.payload_json = {**(m.payload_json or {}), "answer": args.answer, "answered_by": ctx.caller.id,
                          "answered_at": datetime.now(UTC).isoformat()}
    return {"message_id": args.message_id, "answer": args.answer}


class DecideArgs(BaseModel):
    approval_id: int
    decision: Literal["approve", "reject"]
    body: str | None = Field(None, max_length=20000, description="Edited text, if you changed the draft")


@server.tool(callers=HUMAN, roles={"approver"}, input_model=DecideArgs, read_only=False, redact=False)
async def decide_approval(args: DecideArgs, ctx: ToolContext) -> dict:
    """Approve or reject a draft (digest or nudge). Only a person with the approver role can do this.
    Approved drafts are sent by the Notifier; nothing is sent before this."""
    async with session_scope() as session:
        a = await session.get(Approval, args.approval_id)
        if a is None:
            raise ToolError("No such draft")
        if a.status != "pending":
            raise ToolError(f"This draft is already {a.status}")
        if args.body is not None and args.decision == "approve":
            a.draft_json = {**a.draft_json, "body": args.body, "edited_by": ctx.caller.id}
        a.status = "approved" if args.decision == "approve" else "rejected"
        a.decided_by, a.decided_at = ctx.caller.id, datetime.now(UTC)
        session.add(RadarMessage(user_id="role:approver", kind="pill", mood="happy" if a.status == "approved" else None,
                                 body=f"{a.draft_json.get('title')} {a.status} by {ctx.caller.id}",
                                 payload_json={"approval_id": a.id}))
        return _approval(a)


class ListApprovalsArgs(BaseModel):
    status: Literal["pending", "approved", "rejected"] | None = None


@server.tool(callers=HUMAN, roles={"approver", "admin"}, input_model=ListApprovalsArgs, redact=False)
async def list_approvals(args: ListApprovalsArgs, ctx: ToolContext) -> dict:
    """Drafts Radar made, with status, who decided and when, and whether they were sent."""
    async with session_scope() as session:
        q = select(Approval).order_by(Approval.id.desc())
        if args.status:
            q = q.where(Approval.status == args.status)
        return {"approvals": [_approval(a) for a in (await session.scalars(q)).all()]}


class MemoryArgs(BaseModel):
    text: str = Field(min_length=3, max_length=300)


@server.tool(callers={"human", "agent"}, roles={"viewer", "agent"}, input_model=MemoryArgs, read_only=False)
async def remember(args: MemoryArgs, ctx: ToolContext) -> dict:
    """Add a short fact Radar should keep in mind. Everyone can see and remove it in the Radar panel."""
    async with session_scope() as session:
        m = RadarMemory(text=args.text.strip(), created_by=ctx.caller.id)
        session.add(m)
        await session.flush()
        return {"id": m.id, "text": m.text}


class ForgetArgs(BaseModel):
    id: int


@server.tool(callers=HUMAN, roles={"viewer"}, input_model=ForgetArgs, read_only=False)
async def forget(args: ForgetArgs, ctx: ToolContext) -> dict:
    """Remove something from Radar's memory."""
    async with session_scope() as session:
        m = await session.get(RadarMemory, args.id)
        if m is None:
            raise ToolError("Not in memory")
        await session.delete(m)
    return {"removed": args.id}


@server.tool(callers={"human", "agent", "service"}, roles={"viewer", "agent", "radar"})
async def list_memory(args, ctx: ToolContext) -> dict:
    """What Radar remembers."""
    async with session_scope() as session:
        rows = (await session.scalars(select(RadarMemory).order_by(RadarMemory.id))).all()
    return {"memory": [{"id": m.id, "text": m.text} for m in rows]}


# -- Radar (agent and nightly job) ---------------------------------------------

class SaveFindings(BaseModel):
    projects_checked: int = Field(ge=0)
    findings: list[dict[str, Any]]


@server.tool(callers={"service"}, roles={"radar"}, input_model=SaveFindings, read_only=False)
async def save_findings(args: SaveFindings, ctx: ToolContext) -> dict:
    """Store one check's findings. Keeps the first-seen date of findings seen before, and keeps dismissals."""
    now = datetime.now(UTC)
    async with session_scope() as session:
        prev_run = await session.scalar(select(AgentRun).where(AgentRun.ended_at.is_not(None)).order_by(AgentRun.id.desc()))
        prev = {}
        if prev_run:
            for f in (await session.scalars(select(Finding).where(Finding.run_id == prev_run.id))).all():
                prev[(f.evidence_json or {}).get("key")] = f
        codes = {p.code: p.id for p in (await session.scalars(select(Project))).all()}
        run = AgentRun(started_at=now, projects_checked=args.projects_checked)
        session.add(run)
        await session.flush()
        new_keys = []
        for d in args.findings:
            key = d.get("key")
            old = prev.get(key)
            if old is None:
                new_keys.append(key)
            session.add(Finding(
                run_id=run.id, project_id=codes.get(d.get("project_code") or ""), type=d["type"], severity=d["severity"],
                text=d["text"], evidence_json={**(d.get("evidence") or {}), "key": key, "detail": d.get("detail")},
                first_seen_at=old.first_seen_at if old else now,
                dismissed_by=old.dismissed_by if old else None, dismissed_at=old.dismissed_at if old else None))
        run.findings, run.ended_at = len(args.findings), datetime.now(UTC)
        return {"run_id": run.id, "saved": len(args.findings), "new": new_keys}


class PostArgs(BaseModel):
    to: str = Field("*", max_length=200, description="A person's id, '*' for everyone, or 'role:approver'")
    kind: Literal["radar", "ask", "pill", "health", "findings", "dep", "divider"] = "radar"
    body: str = Field("", max_length=8000)
    mood: str | None = Field(None, max_length=16)
    payload: dict[str, Any] = Field(default_factory=dict)
    reply_to: int | None = None


@server.tool(callers=RADAR_WRITERS, roles=RADAR_ROLES, input_model=PostArgs, read_only=False, redact=False)
async def post_message(args: PostArgs, ctx: ToolContext) -> dict:
    """Post a message or card in a conversation. If it answers a question, the question is marked answered."""
    async with session_scope() as session:
        to = args.to
        if args.reply_to is not None:
            q = await session.get(RadarMessage, args.reply_to)
            if q is None or q.kind != "me":
                raise ToolError("reply_to must be a person's message")
            q.state = "answered"
            to = q.user_id
        m = RadarMessage(user_id=to, kind=args.kind, body=args.body, mood=args.mood, payload_json=args.payload,
                         reply_to=args.reply_to)
        session.add(m)
        await session.flush()
        return {"message_id": m.id}


class PendingArgs(BaseModel):
    limit: int = Field(10, ge=1, le=50)


@server.tool(callers=RADAR_WRITERS, roles=RADAR_ROLES, input_model=PendingArgs, redact=False)
async def pending_questions(args: PendingArgs, ctx: ToolContext) -> dict:
    """People's messages Radar has not answered yet, with the last few messages of each conversation."""
    async with session_scope() as session:
        qs = (await session.scalars(select(RadarMessage).where(RadarMessage.kind == "me", RadarMessage.state == "pending")
                                    .order_by(RadarMessage.id).limit(args.limit))).all()
        out = []
        for q in qs:
            ctx_rows = (await session.scalars(select(RadarMessage).where(
                RadarMessage.user_id == q.user_id, RadarMessage.id < q.id, RadarMessage.kind.in_(["me", "radar"]))
                .order_by(RadarMessage.id.desc()).limit(6))).all()
            out.append({"message_id": q.id, "user": q.user_id, "text": q.body,
                        "history": [{"from": "person" if r.kind == "me" else "radar", "text": r.body} for r in reversed(ctx_rows)]})
    return {"questions": out}


class AnsweredAsks(BaseModel):
    since_hours: int = Field(48, ge=1, le=720)


@server.tool(callers=RADAR_WRITERS, roles=RADAR_ROLES, input_model=AnsweredAsks)
async def list_asks(args: AnsweredAsks, ctx: ToolContext) -> dict:
    """Radar's recent questions to approvers, with answers, so Radar can act on a yes."""
    since = datetime.now(UTC) - timedelta(hours=args.since_hours)
    async with session_scope() as session:
        rows = (await session.scalars(select(RadarMessage).where(RadarMessage.kind == "ask",
                                                                 RadarMessage.created_at >= since))).all()
    return {"asks": [{"message_id": r.id, "text": r.body, "payload": r.payload_json or {},
                      "created_at": r.created_at.isoformat()} for r in rows]}


class DraftArgs(BaseModel):
    kind: Literal["digest", "nudge"]
    title: str = Field(min_length=3, max_length=200)
    to: str = Field(min_length=2, max_length=300, description="Recipients and channel, e.g. 'POS03 owner · Teams'")
    body: str = Field(min_length=10, max_length=20000)
    project: str | None = Field(None, max_length=64)
    send_at: str | None = Field(None, description="ISO time to send after approval (empty = as soon as approved)")
    from_ask: int | None = Field(None, description="The question this draft answers, if an approver said yes")


@server.tool(callers=RADAR_WRITERS, roles=RADAR_ROLES, input_model=DraftArgs, read_only=False, redact=False)
async def create_draft(args: DraftArgs, ctx: ToolContext) -> dict:
    """Create a draft for an approver: weekly digest or a nudge to a project owner. Never sends anything."""
    async with session_scope() as session:
        existing = (await session.scalars(select(Approval).where(Approval.status == "pending",
                                                                 Approval.kind == args.kind))).all()
        if any(e.draft_json.get("title") == args.title for e in existing):
            raise ToolError("The same draft is already waiting for approval")
        if args.from_ask is not None:
            ask = await session.get(RadarMessage, args.from_ask)
            if ask is None or ask.kind != "ask" or (ask.payload_json or {}).get("answer") != "yes":
                raise ToolError("from_ask must be a question an approver answered yes")
            if (ask.payload_json or {}).get("draft_id"):
                raise ToolError("A draft was already made for this question")
        a = Approval(kind=args.kind, status="pending", created_by=ctx.caller.id,
                     draft_json={"title": args.title, "to": args.to, "body": args.body, "project": args.project,
                                 "send_at": args.send_at})
        session.add(a)
        await session.flush()
        session.add(RadarMessage(user_id="role:approver", kind="approval", mood="asking", body=args.body,
                                 payload_json={"approval_id": a.id}))
        if args.from_ask is not None:
            ask.payload_json = {**ask.payload_json, "draft_id": a.id}
        run = await session.scalar(select(AgentRun).order_by(AgentRun.id.desc()))
        if run:
            run.drafts += 1
        return {"approval_id": a.id, "status": "pending"}


class DismissArgs(BaseModel):
    finding_id: int


@server.tool(callers=HUMAN, roles={"approver", "admin"}, input_model=DismissArgs, read_only=False)
async def dismiss_finding(args: DismissArgs, ctx: ToolContext) -> dict:
    """Dismiss a finding. It stays dismissed in later checks while the same problem remains."""
    async with session_scope() as session:
        f = await session.get(Finding, args.finding_id)
        if f is None:
            raise ToolError("No such finding")
        f.dismissed_by, f.dismissed_at = ctx.caller.id, datetime.now(UTC)
    return {"dismissed": args.finding_id}


@server.tool(callers=RADAR_WRITERS, roles=RADAR_ROLES, redact=False)
async def get_llm_config(args, ctx: ToolContext) -> dict:
    """Which LLM Radar uses for its words (set in Admin → Connections): address, model and the *name* of the API key
    secret. Empty address = rule-based answers."""
    from app import integrations

    async with session_scope() as session:
        cfg, saved = await integrations.load(session, "llm", ctx.settings)
    return {**cfg.model_dump(mode="json"), "saved_in_admin": saved}
