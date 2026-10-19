"""The Notifier: sends drafts a person approved. It reads them through
`/notify/mcp` with its own service token and records each result there.

Channels:
- Microsoft Teams: an incoming webhook (TEAMS_WEBHOOK_URL)
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


async def run_notifier(reader: SourceReader, settings: Settings) -> int:
    ready = (await reader.call("notify", "list_ready"))["ready"]
    for item in ready:
        ok, channels, detail = await send_one(settings, item)
        await reader.call("notify", "mark_sent", {"approval_id": item["id"], "ok": ok, "channels": channels,
                                                  "detail": detail})
        log.info("draft %s %s via %s %s", item["id"], "sent" if ok else "NOT sent", channels, detail)
    return len(ready)
