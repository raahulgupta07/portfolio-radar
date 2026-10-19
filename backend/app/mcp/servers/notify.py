"""`/notify/mcp`: what the Notifier may see and do. It only ever sees drafts a
person approved, and only records the result of sending them."""

from datetime import UTC, datetime

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
        send_at = a.draft_json.get("send_at")
        if send_at and datetime.fromisoformat(send_at) > now:
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
