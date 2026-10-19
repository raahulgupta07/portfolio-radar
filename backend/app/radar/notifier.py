"""The Notifier: sends drafts a person approved. It reads them through
`/notify/mcp` with its own service token and records each result there.

Channels:
- Microsoft Teams: an incoming webhook (TEAMS_WEBHOOK_URL)
- Teams chat: Radar's answers to questions people asked the bot in a 1:1 chat go back to that chat
  (deliver_teams_replies). Like the chat in the app, these need no approval: they go only to the person who asked
- Email: SMTP (SMTP_HOST ...), to NOTIFY_EMAIL_TO
- Dev outbox: when no channel is set and APP_ENV=dev, messages are written to
  the log instead, so the flow can be tried end to end
"""

from __future__ import annotations

import asyncio
import logging
import smtplib
from email.message import EmailMessage

import httpx

from app.adapter.readers import SourceReader
from app.settings import Settings
from app.teams.botframework import BotAuthError, BotConnector

log = logging.getLogger("notifier")


def _send_email(settings: Settings, subject: str, body: str) -> None:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.smtp_from
    msg["To"] = ", ".join(settings.notify_email_to)
    msg.set_content(body)
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as s:
        s.starttls()
        if settings.smtp_user:
            s.login(settings.smtp_user, settings.smtp_password)
        s.send_message(msg)


async def send_one(settings: Settings, item: dict) -> tuple[bool, list[str], str]:
    subject = f"[Portfolio Radar] {item['title']}"
    body = f"{item['body']}\n\n— Drafted by Radar, approved by {item.get('approved_by')}. Read-only portfolio tracker."
    sent, errors = [], []
    if settings.teams_webhook_url:
        try:
            async with httpx.AsyncClient(timeout=30) as c:
                r = await c.post(settings.teams_webhook_url, json={"text": f"**{subject}**\n\n{body}"})
                r.raise_for_status()
            sent.append("teams")
        except httpx.HTTPError as e:
            errors.append(f"Teams: {type(e).__name__}")
    if settings.smtp_host and settings.notify_email_to:
        try:
            await asyncio.to_thread(_send_email, settings, subject, body)
            sent.append("email")
        except (OSError, smtplib.SMTPException) as e:
            errors.append(f"Email: {type(e).__name__}")
    if not settings.teams_webhook_url and not settings.smtp_host:
        if settings.app_env in ("dev", "test"):
            log.info("DEV OUTBOX → %s | %s\n%s", item.get("to"), subject, body)
            sent.append("dev outbox")
        else:
            errors.append("No channel set up (TEAMS_WEBHOOK_URL or SMTP_HOST)")
    return bool(sent) and not errors, sent, "; ".join(errors)


_bot: tuple[tuple[str, str, str], BotConnector] | None = None


def _connector(settings: Settings, transport: httpx.AsyncBaseTransport | None) -> BotConnector | None:
    """The Teams bot connector, kept between runs so its sign-in token is reused."""
    global _bot
    key = (settings.teams_bot_app_id, settings.teams_bot_password, settings.entra_tenant_id)
    if not all(key):
        return None
    if _bot is None or _bot[0] != key or transport is not None:
        _bot = (key, BotConnector(*key, transport=transport))
    return _bot[1]


async def deliver_teams_replies(reader: SourceReader, settings: Settings,
                                transport: httpx.AsyncBaseTransport | None = None) -> int:
    """Radar's answers to questions asked in Teams, back to the same 1:1 chat."""
    connector = _connector(settings, transport)
    if connector is None:
        return 0
    replies = (await reader.call("notify", "teams_replies"))["replies"]
    for r in replies:
        try:
            await connector.send(r["service_url"], r["conversation_id"], r["text"], r.get("reply_to_activity"))
            ok, detail = True, ""
        except (BotAuthError, httpx.HTTPError) as e:
            ok, detail = False, f"{type(e).__name__}: {e}"[:300]
        await reader.call("notify", "mark_teams_sent", {"message_id": r["message_id"], "ok": ok, "detail": detail})
        if not ok:
            log.warning("Teams answer %s not delivered: %s", r["message_id"], detail)
    return len(replies)


async def run_notifier(reader: SourceReader, settings: Settings) -> int:
    ready = (await reader.call("notify", "list_ready"))["ready"]
    for item in ready:
        ok, channels, detail = await send_one(settings, item)
        await reader.call("notify", "mark_sent", {"approval_id": item["id"], "ok": ok, "channels": channels,
                                                  "detail": detail})
        log.info("draft %s %s via %s %s", item["id"], "sent" if ok else "NOT sent", channels, detail)
    return len(ready)
