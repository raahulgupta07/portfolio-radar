"""`/admin/mcp`, part 2: set up every connection from the app (Admin →
Connections and Agents). Human admins only, like the rest of `/admin`.

- Source trackers: site, sign-in, token, status mapping, a full check
- Secrets: pasted once, stored in the secret store, never returned or logged
- Outside services: City SSO, the LLM for Radar, Teams, email, each with a test
- Agents: CityGPT, Claude or another City agent signing in with its own Entra app

None of these tools can change project data or write to a tracker.
"""

from __future__ import annotations

import asyncio
import re
import smtplib
import ssl
from datetime import UTC, datetime, time, timedelta
from email.message import EmailMessage
from typing import Any, Literal
from zoneinfo import ZoneInfo

import httpx
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import func, select

from app import integrations
from app.adapter.readers import GatewayReader, SourceCallError
from app.adapter.sync import APP_STATUSES, STATUS_MAP_KEY, load_status_map, match_prefix
from app.connectors import SOURCES
from app.connectors import fields as field_map
from app.db import session_scope
from app.integrations import GUID, Name
from app.mcp import agents as agent_dir
from app.mcp.guard import ToolError
from app.mcp.registry import ToolContext
from app.mcp.servers.admin import ADAPTER, CALLERS, ROLES, SourceArg, SourceId, server
from app.models.app import Prefix, Setting, Source
from app.models.mcp import McpAgent, McpCall, McpTool, McpToolChange
from app.secretstore import KV_PATTERN, SecretError, is_set, kv_name, resolve
from app.portfolio.queries import sync_status
from app.settings import llm_headers

AUTH_METHODS = {"jira": {"api_token", "pat"}, "openproject": {"api_key"}, "multica": {"token"}}
APP_STATUS = Literal["Not started", "In progress", "Done", "On hold"]


def _store(ctx: ToolContext):
    store = ctx.services.get("secrets")
    if store is None:
        raise ToolError("No secret store is set up on the gateway")
    return store


def _http(ctx: ToolContext, timeout: float = 20) -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=timeout, transport=ctx.services.get("http_transport"))


def _today_start(ctx: ToolContext) -> datetime:
    tz = ZoneInfo(ctx.settings.timezone)
    return datetime.combine(datetime.now(tz).date(), time.min, tzinfo=tz).astimezone(UTC)


def _changed(ctx: ToolContext, source_id: str | None = None) -> None:
    """Make live connectors use a saved change at once instead of within a minute."""
    for sid, c in (ctx.services.get("connectors") or {}).items():
        if source_id in (None, sid) and hasattr(c, "invalidate"):
            c.invalidate()


def _moved(old: str, new: str) -> bool:
    """A saved address changed to a different one (setting it the first time is not a move)."""
    return bool(old) and old.rstrip("/").lower() != new.rstrip("/").lower()


WRITTEN_KEY = "secrets_written"  # app.setting: secret name → when set_secret last saved it
JUST_WRITTEN = timedelta(minutes=15)


async def _just_written(session, ref: str) -> bool:
    """Whether a person pasted this secret in the last few minutes (so it is meant for the new address)."""
    row = await session.get(Setting, WRITTEN_KEY)
    at = (row.value or {}).get(ref) if row else None
    return bool(at) and datetime.now(UTC) - datetime.fromisoformat(at) < JUST_WRITTEN


# Where each service's secret is sent: changing that address needs the secret pasted again.
SECRET_HOST = {"llm": ("base_url", "api_key_ref"), "email": ("smtp_host", "password_ref")}


def _err(e: ValidationError) -> ToolError:
    err = e.errors()[0]
    return ToolError(f"{'.'.join(str(x) for x in err['loc']) or 'input'}: {err['msg']}")


async def _tool_counts(session) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {}
    for srv, status, n in (await session.execute(
            select(McpTool.server, McpTool.status, func.count()).group_by(McpTool.server, McpTool.status))).all():
        c = out.setdefault(srv, {"on": 0, "off": 0, "review": 0, "total": 0})
        c[status] = c.get(status, 0) + n
        c["total"] += n
    return out


def _service_status(name: str, cfg: Any, secret_ok: bool) -> str:
    if not cfg.ready():
        return "rules_only" if name == "llm" else "not_set"
    return "ready" if secret_ok else "secret_missing"


async def _services(ctx: ToolContext, session) -> dict[str, Any]:
    store = _store(ctx)
    out = {}
    for name in ("sso", "llm", "teams", "email"):
        cfg, saved = await integrations.load(session, name, ctx.settings)
        ref = {"llm": "api_key_ref", "teams": "webhook_ref", "email": "password_ref"}.get(name)
        secret_ok = True if ref is None or not getattr(cfg, ref) else await is_set(store, getattr(cfg, ref))
        if name == "llm" and cfg.ready() and not getattr(cfg, ref):
            secret_ok = True  # some endpoints need no key
        out[name] = {"status": _service_status(name, cfg, secret_ok), "saved_in_admin": saved,
                     "config": cfg.model_dump(mode="json"),
                     **({"secret_set": secret_ok} if ref else {})}
        if name == "teams":  # two-way chat, separate from the webhook
            out[name]["bot_status"] = ("not_set" if not cfg.bot_ready() else
                                       "ready" if await is_set(store, cfg.bot_password_ref) else "secret_missing")
    return out


# -- overview -----------------------------------------------------------------

@server.tool(callers=CALLERS, roles=ROLES, redact=False)
async def get_connections(args, ctx: ToolContext) -> dict:
    """Everything on the Connections page in one call: gateway summary, source trackers (with secret names and
    whether each secret is set), app servers with tool counts, and outside services (SSO, LLM, Teams, email)."""
    store = _store(ctx)
    since = _today_start(ctx)
    async with session_scope() as session:
        status = await sync_status(session)
        rows = {s.id: s for s in (await session.scalars(select(Source))).all()}
        counts = await _tool_counts(session)
        pending = await session.scalar(select(func.count()).select_from(McpToolChange).where(McpToolChange.status == "pending"))
        calls = dict((await session.execute(select(McpCall.outcome, func.count()).where(McpCall.at >= since)
                                            .group_by(McpCall.outcome))).all())
        services = await _services(ctx, session)
    registry = ctx.services["gateway"].registry
    sources = []
    for s in status["sources"]:
        row = rows.get(s["id"])
        sources.append({**s, "base_url": row.base_url if row else "", "secret_ref": row.secret_ref if row else "",
                        "secret_set": await is_set(store, row.secret_ref) if row and row.secret_ref else False,
                        "flavor": row.flavor if row else "", "enabled": row.enabled if row else False,
                        "unmapped_statuses": row.unmapped_statuses if row else [],
                        "tools": counts.get(s["id"], {"on": 0, "off": 0, "review": 0, "total": 0})})
    servers = [{"server": n, "title": d.title, "description": d.description, "owner": d.owner,
                "tools": counts.get(n, {"on": 0, "off": 0, "review": 0, "total": 0})}
               for n, d in registry.servers.items() if d.direction == "out"]
    total = sum(c["total"] for c in counts.values())
    return {
        "summary": {"servers": len(registry.servers), "tools": total, "tools_on": sum(c["on"] for c in counts.values()),
                    "changes_to_review": pending or 0, "calls_today": sum(calls.values()),
                    "blocked_today": calls.get("denied", 0), "secret_store": store.kind,
                    "source_mode": ctx.settings.source_mode},
        "sources": sources, "servers": servers, "services": services,
    }


# -- source trackers ----------------------------------------------------------

@server.tool(callers=CALLERS, roles=ROLES, input_model=SourceArg, redact=False)
async def get_source(args: SourceArg, ctx: ToolContext) -> dict:
    """One source tracker for its set-up page: connection details, whether its secret is set, status mapping
    (tracker status → app status, with statuses seen but not mapped), and the tools on its server."""
    async with session_scope() as session:
        row = await session.get(Source, args.source)
        if row is None:
            raise ToolError(f"No source {args.source}")
        smap = await load_status_map(session, ctx.settings)
        fields = await field_map.load(session, args.source)
        tools = (await session.scalars(select(McpTool).where(McpTool.server == args.source).order_by(McpTool.name))).all()
    mapping = []
    seen = set()
    for scope in (args.source, "default"):
        for k, v in smap.raw.get(scope, {}).items():
            if k.lower() not in seen:
                seen.add(k.lower())
                mapping.append({"tracker_status": k, "app_status": v, "from": "source" if scope == args.source else "default"})
    unmapped = [s for s in row.unmapped_statuses if s.lower() not in seen]
    return {
        "source": row.id, "name": row.name, "team": row.team, "type": row.type, "enabled": row.enabled,
        "base_url": row.base_url, "flavor": row.flavor, "auth_method": row.auth_method, "account": row.account,
        "secret_ref": row.secret_ref, "secret_set": await is_set(_store(ctx), row.secret_ref) if row.secret_ref else False,
        "auth_methods": sorted(AUTH_METHODS[row.id]), "source_mode": ctx.settings.source_mode,
        "last_status": row.last_status, "last_error": row.last_error,
        "last_sync_at": row.last_sync_at.isoformat() if row.last_sync_at else None,
        "app_statuses": list(APP_STATUSES), "mapping": mapping, "unmapped": unmapped,
        "fields": None if fields is None else {
            "values": fields.fields, "confirmed_by": fields.confirmed_by, "confirmed_at": fields.confirmed_at,
            "about": field_map.describe(args.source)},
        "tools": [{"tool": t.name, "status": t.status, "callers": t.callers, "roles": t.roles,
                   "description": t.description} for t in tools],
    }


class SourceSettings(BaseModel):
    source: SourceId
    base_url: str = Field("", max_length=500, pattern=r"^$|^https://[^\s/$.?#][^\s]*$",
                          description="The tracker's address, https only")
    flavor: Literal["", "cloud", "datacenter"] = ""
    auth_method: str = Field("", max_length=32)
    account: str = Field("", max_length=200, description="The service account the read-only token belongs to")
    secret_ref: str = Field("", pattern=KV_PATTERN, description="Name of the token in the secret store, e.g. kv://jira-read-token")
    enabled: bool = True


@server.tool(callers=CALLERS, roles=ROLES, input_model=SourceSettings, read_only=False, redact=False)
async def save_source(args: SourceSettings, ctx: ToolContext) -> dict:
    """Save a source tracker's connection: address, JIRA cloud or data center, sign-in method, service account and
    the name of its read-only token. The token itself is saved with set_secret. Used from the next sync."""
    if args.auth_method and args.auth_method not in AUTH_METHODS[args.source]:
        raise ToolError(f"Sign-in for {args.source} must be one of {', '.join(sorted(AUTH_METHODS[args.source]))}")
    if args.flavor and args.source != "jira":
        raise ToolError("Cloud or data center applies to JIRA only")
    async with session_scope() as session:
        row = await session.get(Source, args.source)
        if row is None:
            raise ToolError(f"No source {args.source}")
        if (_moved(row.base_url, args.base_url) and row.secret_ref and args.secret_ref == row.secret_ref
                and not await _just_written(session, row.secret_ref)):
            raise ToolError("The address changed. Paste the token again, so the saved one is never sent to a new host")
        row.base_url, row.flavor, row.auth_method = args.base_url, args.flavor, args.auth_method
        row.account, row.secret_ref, row.enabled = args.account, args.secret_ref, args.enabled
    _changed(ctx, args.source)
    return {"source": args.source, "saved": True}


class SecretValue(BaseModel):
    ref: str = Field(pattern=r"^kv://[a-z0-9][a-z0-9-]{0,99}$", description="Where to keep it, e.g. kv://jira-read-token")
    value: str = Field(min_length=1, max_length=8000, description="The secret. Stored, never shown or logged")


@server.tool(callers=CALLERS, roles=ROLES, input_model=SecretValue, read_only=False, secret_args={"value"})
async def set_secret(args: SecretValue, ctx: ToolContext) -> dict:
    """Save a secret (token, API key, webhook URL, password) in the secret store. The value is never returned or
    written to the audit log; afterwards only its name is shown."""
    store = _store(ctx)
    try:
        await store.set(kv_name(args.ref), args.value.strip())
    except SecretError as e:
        raise ToolError(str(e)) from e
    async with session_scope() as session:
        row = await session.get(Setting, WRITTEN_KEY)
        written = {**(row.value if row else {}), args.ref: datetime.now(UTC).isoformat()}
        if row is None:
            session.add(Setting(key=WRITTEN_KEY, value=written, updated_by=ctx.caller.id))
        else:
            row.value, row.updated_by = written, ctx.caller.id
    _changed(ctx)
    return {"ref": args.ref, "saved": True, "store": store.kind}


@server.tool(callers=CALLERS, roles=ROLES, input_model=SourceArg, redact=False)
async def check_source(args: SourceArg, ctx: ToolContext) -> dict:
    """Check a source end to end without changing anything: token set, tracker reachable, projects found, names
    that match a prefix, names with no prefix, and statuses with no mapping."""
    checks: list[dict[str, Any]] = []
    async with session_scope() as session:
        row = await session.get(Source, args.source)
        if row is None:
            raise ToolError(f"No source {args.source}")
        prefixes = [p.value for p in (await session.scalars(select(Prefix).where(Prefix.active.is_(True)))).all()]
        smap = await load_status_map(session, ctx.settings)
        fields = await field_map.load(session, args.source)
    if ctx.settings.source_mode == "live":
        if fields is None:
            checks.append({"check": "Connector", "ok": False, "detail": "No live connector yet: its API is needed"})
        else:
            checks.append({"check": "Field mapping", "ok": fields.confirmed,
                           "detail": f"Confirmed by {fields.confirmed_by}" if fields.confirmed else "Not confirmed yet"})
    if ctx.settings.source_mode == "mock":
        checks.append({"check": "Data", "ok": True, "detail": "Sample data (SOURCE_MODE=mock)"})
    elif not row.secret_ref:
        checks.append({"check": "Read token", "ok": False, "detail": "No token name set"})
    else:
        ok = await is_set(_store(ctx), row.secret_ref)
        checks.append({"check": "Read token", "ok": ok, "detail": row.secret_ref if ok else f"{row.secret_ref} is empty"})

    reader = GatewayReader(ctx.services["gateway"], ADAPTER)
    started = datetime.now(UTC)
    try:
        listing = await reader.call(args.source, "list_projects")
    except SourceCallError as e:
        checks.append({"check": "Tracker reached", "ok": False, "detail": str(e)})
        return {"source": args.source, "ok": False, "checks": checks, "checked_at": started.isoformat()}
    ms = int((datetime.now(UTC) - started).total_seconds() * 1000)
    checks.append({"check": "Tracker reached", "ok": True, "detail": f"{ms} ms, read-only"})
    projects = listing["projects"]
    checks.append({"check": "Projects found", "ok": True, "detail": str(len(projects))})
    matched, no_prefix = [], []
    for p in projects:
        m = match_prefix(p["name"], prefixes)
        (matched if m.code else no_prefix).append(p)
    checks.append({"check": "Match a prefix", "ok": bool(matched) or not projects, "detail": str(len(matched))})
    checks.append({"check": "Names with no prefix", "ok": not no_prefix,
                   "detail": ", ".join(p["name"] for p in no_prefix[:5]) or "none"})
    unmapped: set[str] = set()
    for p in matched[:40]:
        try:
            status = (await reader.call(args.source, "get_project", {"key": p["key"], "fields": ["status"]}))["status"]
        except SourceCallError:
            continue
        if smap.map(args.source, status) is None:
            unmapped.add(status.strip())
    checks.append({"check": "Statuses with no mapping", "ok": not unmapped, "detail": ", ".join(sorted(unmapped)) or "none"})
    if unmapped:
        async with session_scope() as session:
            src = await session.get(Source, args.source)
            src.unmapped_statuses = sorted(set(src.unmapped_statuses) | unmapped)
    return {"source": args.source, "ok": all(c["ok"] for c in checks if c["check"] != "Names with no prefix"),
            "checks": checks, "checked_at": started.isoformat(), "unmapped": sorted(unmapped)}


class FieldMappingArgs(BaseModel):
    source: Literal["jira", "openproject", "multica"]
    mapping: dict[str, Any] = Field(description="Where each app field comes from; see get_source → fields.about")
    confirm: bool = Field(False, description="True = a person checked this against the tracker. Live sync needs it")


@server.tool(callers=CALLERS, roles=ROLES, input_model=FieldMappingArgs, read_only=False)
async def save_field_mapping(args: FieldMappingArgs, ctx: ToolContext) -> dict:
    """Save where a tracker keeps each project field (status, dates, owner, % done, strategy tag, risks).
    A live sync uses it only once a person confirms it; saving without confirm clears the confirmation."""
    try:
        async with session_scope() as session:
            m = await field_map.save(session, args.source, args.mapping, ctx.caller.id, args.confirm)
    except ValidationError as e:
        raise _err(e) from e
    _changed(ctx, args.source)
    return {"source": args.source, "saved": True, "confirmed": m.confirmed, "mapping": m.fields}


class MappingArgs(BaseModel):
    source: Literal["default", "jira", "openproject", "multica"]
    mapping: dict[str, APP_STATUS] = Field(description="Tracker status → app status, e.g. {\"UAT\": \"In progress\"}. "
                                                       "Replaces this section of the mapping")


@server.tool(callers=CALLERS, roles=ROLES, input_model=MappingArgs, read_only=False)
async def save_status_mapping(args: MappingArgs, ctx: ToolContext) -> dict:
    """Save how one source's statuses map to the app's four statuses (Not started, In progress, Done, On hold).
    'default' applies to every source. Projects with an unmapped status do not sync; nothing is guessed."""
    clean = {k.strip(): v for k, v in args.mapping.items() if k.strip()}
    if any(len(k) > 60 for k in clean):
        raise ToolError("A status name is longer than 60 characters")
    async with session_scope() as session:
        current = (await load_status_map(session, ctx.settings)).raw
        current[args.source] = clean
        row = await session.get(Setting, STATUS_MAP_KEY)
        if row is None:
            session.add(Setting(key=STATUS_MAP_KEY, value=current, updated_by=ctx.caller.id))
        else:
            row.value, row.updated_by = current, ctx.caller.id
        if args.source != "default":
            src = await session.get(Source, args.source)
            if src is not None:
                src.unmapped_statuses = [s for s in src.unmapped_statuses if s.lower() not in {k.lower() for k in clean}]
    return {"source": args.source, "statuses": len(clean)}


# -- outside services ---------------------------------------------------------

class IntegrationName(BaseModel):
    name: Name


class IntegrationArgs(IntegrationName):
    config: dict[str, Any] = Field(description="All fields of that service's settings")


@server.tool(callers=CALLERS, roles=ROLES, redact=False)
async def get_integrations(args, ctx: ToolContext) -> dict:
    """Settings for City SSO, the LLM for Radar, Microsoft Teams and email: values, whether each secret is set,
    and status (ready, not_set, rules_only, secret_missing). Secrets are shown by name only."""
    async with session_scope() as session:
        services = await _services(ctx, session)
    return {"services": services, "secret_store": _store(ctx).kind}


@server.tool(callers=CALLERS, roles=ROLES, input_model=IntegrationArgs, read_only=False, redact=False)
async def save_integration(args: IntegrationArgs, ctx: ToolContext) -> dict:
    """Save the settings of one outside service (sso, llm, teams or email). Secrets go in as names (kv://…).
    SSO changes apply to sign-in at once; the others from the next run."""
    try:
        async with session_scope() as session:
            if args.name in SECRET_HOST:
                host, ref = SECRET_HOST[args.name]
                old, saved = await integrations.load(session, args.name, ctx.settings)
                if (saved and getattr(old, ref) and args.config.get(ref) == getattr(old, ref)
                        and _moved(getattr(old, host), str(args.config.get(host, "")))
                        and not await _just_written(session, getattr(old, ref))):
                    raise ToolError(f"The {host.replace('_', ' ')} changed. Paste the secret again, so the saved one "
                                    "is never sent to a new host")
            cfg = await integrations.save(session, args.name, args.config, ctx.caller.id)
    except ValidationError as e:
        raise _err(e) from e
    if args.name == "sso" and "directory" in ctx.services:
        await agent_dir.refresh(ctx.services["directory"])
    return {"name": args.name, "config": cfg.model_dump(mode="json")}


async def _test_sso(cfg, ctx) -> tuple[bool, str]:
    if cfg.provider == "keycloak":
        if not cfg.issuer:
            return False, "Add the realm address first"
        base = (cfg.internal_url or cfg.issuer).rstrip("/")
        async with _http(ctx) as c:
            r = await c.get(f"{base}/.well-known/openid-configuration")
            if r.status_code != 200:
                return False, f"Keycloak did not answer for this realm (HTTP {r.status_code})"
            if r.json().get("issuer", "").rstrip("/") != cfg.issuer.rstrip("/"):
                return False, "The realm answered with a different issuer address. Check the address people use"
            keys = await c.get(f"{base}/protocol/openid-connect/certs")
        if keys.status_code != 200 or not keys.json().get("keys"):
            return False, "The realm publishes no signing keys"
        return True, "Realm found. Sign-in keys are published" + ("" if cfg.audience else ". Add the gateway audience")
    if not cfg.tenant_id:
        return False, "Add the tenant ID first"
    url = f"https://login.microsoftonline.com/{cfg.tenant_id}/v2.0/.well-known/openid-configuration"
    async with _http(ctx) as c:
        r = await c.get(url)
    if r.status_code != 200:
        return False, f"Entra ID did not recognise this tenant (HTTP {r.status_code})"
    issuer = r.json().get("issuer", "")
    if cfg.tenant_id.lower() not in issuer.lower():
        return False, "The tenant answered with a different issuer"
    return True, "Tenant found. Sign-in keys are published" + ("" if cfg.audience else ". Add the gateway audience")


async def _test_llm(cfg, ctx) -> tuple[bool, str]:
    if not cfg.ready():
        return False, "Add the address and model first. Until then Radar answers from rules"
    key = await resolve(_store(ctx), cfg.api_key_ref)
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    if cfg.provider == "openrouter":
        headers.update(llm_headers(ctx.settings.model_copy(update={"llm_provider": "openrouter"})))
    async with _http(ctx, timeout=60) as c:
        r = await c.post(cfg.base_url.rstrip("/") + "/chat/completions", headers=headers, json={
            "model": cfg.model, "max_tokens": 20, "temperature": 0,
            "messages": [{"role": "user", "content": "Reply with the single word OK."}]})
    if r.status_code != 200:
        return False, f"The LLM answered HTTP {r.status_code}" + (" (check the API key)" if r.status_code in (401, 403) else "")
    text = (r.json().get("choices") or [{}])[0].get("message", {}).get("content", "")
    return True, f"The model answered: {str(text).strip()[:60]}"


async def _test_teams(cfg, ctx) -> tuple[bool, str]:
    """The webhook gets one test message; the chat bot (if set) signs in to the Bot Framework."""
    if not cfg.webhook_ref and not cfg.bot_ready():
        return False, "Set the webhook, the chat bot, or both"
    parts, ok = [], True
    if cfg.webhook_ref:
        url = await resolve(_store(ctx), cfg.webhook_ref)
        if not url:
            ok = False
            parts.append("Webhook: the secret is empty. Paste the webhook URL first")
        else:
            async with _http(ctx) as c:
                r = await c.post(url, json={"text": f"Test from Portfolio Radar Admin, sent by {ctx.caller.id}. "
                                                    "Radar sends here only after a person approves."})
            ok = ok and r.status_code < 300
            parts.append("Webhook: test message sent" if r.status_code < 300 else f"Webhook: Teams answered HTTP {r.status_code}")
    if cfg.bot_ready():
        from app.teams.botframework import BotAuthError, BotConnector

        async with session_scope() as session:
            sso, _ = await integrations.load(session, "sso", ctx.settings)
        password = await resolve(_store(ctx), cfg.bot_password_ref)
        if not sso.tenant_id:
            ok = False
            parts.append("Chat bot: set the City tenant under Sign-in first")
        elif not password:
            ok = False
            parts.append("Chat bot: the client secret is empty")
        else:
            bot = BotConnector(cfg.bot_app_id, password, sso.tenant_id, transport=ctx.services.get("http_transport"))
            try:
                async with _http(ctx) as c:
                    await bot._bearer(c)
                parts.append("Chat bot: signed in to the Bot Framework")
            except BotAuthError as e:
                ok = False
                parts.append(f"Chat bot: {e}")
    return ok, ". ".join(parts)


async def _test_email(cfg, ctx) -> tuple[bool, str]:
    if not cfg.smtp_host:
        return False, "Add the SMTP server first"
    to = ctx.caller.id if "@" in ctx.caller.id else (cfg.recipients[0] if cfg.recipients else "")
    if not to:
        return False, "Add a recipient first"
    password = await resolve(_store(ctx), cfg.password_ref)
    sender = ctx.services.get("smtp_send") or _smtp_send
    try:
        await asyncio.to_thread(sender, cfg, password, to)
    except (OSError, smtplib.SMTPException) as e:
        return False, f"Email failed: {type(e).__name__}"
    return True, f"Test email sent to {to}"


def _smtp_send(cfg, password: str, to: str) -> None:
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = "[Portfolio Radar] Test email", cfg.sender, to
    msg.set_content("Test from Portfolio Radar Admin. Radar sends email only after a person approves.")
    with smtplib.SMTP(cfg.smtp_host, cfg.smtp_port, timeout=30) as s:
        s.starttls(context=ssl.create_default_context())  # check the server's certificate
        if cfg.username:
            s.login(cfg.username, password)
        s.send_message(msg)


@server.tool(callers=CALLERS, roles=ROLES, input_model=IntegrationName, read_only=False)
async def test_integration(args: IntegrationName, ctx: ToolContext) -> dict:
    """Test one outside service with its saved settings: SSO finds the tenant, the LLM answers one word, Teams and
    email send one test message (email to you)."""
    async with session_scope() as session:
        cfg, _ = await integrations.load(session, args.name, ctx.settings)
    test = {"sso": _test_sso, "llm": _test_llm, "teams": _test_teams, "email": _test_email}[args.name]
    try:
        ok, detail = await test(cfg, ctx)
    except httpx.HTTPError as e:
        ok, detail = False, f"Could not connect ({type(e).__name__})"
    except SecretError as e:
        ok, detail = False, str(e)
    return {"name": args.name, "ok": ok, "detail": detail}


# -- agents -------------------------------------------------------------------

class AgentArgs(BaseModel):
    id: int | None = Field(None, description="Leave out to add a new agent")
    name: str = Field(min_length=2, max_length=100)
    kind: Literal["agent", "service"] = "agent"
    app_id: str = Field(pattern=r"^[\w.:/@-]{1,200}$",
                        description="The Entra application (client) ID, or the Keycloak client ID, the agent signs in with")
    roles: list[str] = Field(default_factory=lambda: ["agent"])
    servers: list[str] = Field(min_length=1, description="Servers it may use; omni and system are always allowed")
    rate_limit: int = Field(120, ge=1, le=2000, description="Calls per minute")
    enabled: bool = True


class AgentId(BaseModel):
    id: int


class AgentEnabled(AgentId):
    enabled: bool


def _agent_dict(a: McpAgent, calls: dict[str, tuple[int, Any]]) -> dict:
    n, last = calls.get(a.caller_id, (0, None))
    return {"id": a.id, "caller_id": a.caller_id, "name": a.name, "kind": a.kind, "app_id": a.app_id,
            "roles": a.roles, "servers": a.servers, "rate_limit": a.rate_limit, "enabled": a.enabled,
            "built_in": False, "calls_today": n, "last_call_at": last.isoformat() if last else None,
            "created_by": a.created_by}


@server.tool(callers=CALLERS, roles=ROLES, redact=False)
async def list_agents(args, ctx: ToolContext) -> dict:
    """Agents and services that use the gateway: built-in ones (Radar, nightly sync, Notifier) and ones set up in
    Admin (CityGPT, Claude, other City agents), with the servers each may use and calls today."""
    since = _today_start(ctx)
    async with session_scope() as session:
        rows = (await session.scalars(select(McpAgent).order_by(McpAgent.name))).all()
        calls = {cid: (n, last) for cid, n, last in (await session.execute(
            select(McpCall.caller_id, func.count(), func.max(McpCall.at)).where(McpCall.at >= since)
            .group_by(McpCall.caller_id))).all()}
    built_in = []
    for b in agent_dir.BUILT_IN:
        n, last = calls.get(b["caller_id"], (0, None))
        built_in.append({**b, "built_in": True, "calls_today": n, "last_call_at": last.isoformat() if last else None})
    servers = [{"server": n, "title": d.title, "direction": d.direction}
               for n, d in ctx.services["gateway"].registry.servers.items() if n not in ("omni", "system", "admin")]
    return {"agents": [_agent_dict(a, calls) for a in rows], "built_in": built_in, "servers": servers,
            "roles": agent_dir.AGENT_ROLES}


@server.tool(callers=CALLERS, roles=ROLES, input_model=AgentArgs, read_only=False, redact=False)
async def save_agent(args: AgentArgs, ctx: ToolContext) -> dict:
    """Add or change an agent: its Entra app ID, kind (agent or service), roles, the servers it may use and its rate
    limit. Agents can never approve or send; the guard enforces that whatever is set here."""
    registry = ctx.services["gateway"].registry
    bad_roles = set(args.roles) - set(agent_dir.AGENT_ROLES[args.kind])
    if bad_roles or not args.roles:
        raise ToolError(f"A {args.kind} may only have the roles {', '.join(agent_dir.AGENT_ROLES[args.kind])}")
    bad_servers = [s for s in args.servers if s not in registry.servers or s == "admin"]
    if bad_servers:
        raise ToolError(f"Not a server an agent may use: {', '.join(bad_servers)}")
    caller_id = agent_dir.slug(args.name)
    if not caller_id or caller_id in {b["caller_id"] for b in agent_dir.BUILT_IN}:
        raise ToolError("Choose another name")
    # Entra IDs are GUIDs (any case); Keycloak client IDs are names and keep their case.
    app_id = args.app_id.lower() if re.fullmatch(GUID[4:], args.app_id) else args.app_id
    if app_id in {k.lower() for k in ctx.settings.entra_apps}:
        raise ToolError("This app is already set up in ENTRA_APPS on the gateway")
    async with session_scope() as session:
        for other in (await session.scalars(select(McpAgent))).all():
            if other.id != args.id and (other.app_id == app_id or other.caller_id == caller_id):
                raise ToolError("Another agent already has this name or app ID")
        if args.id is None:
            row = McpAgent(created_by=ctx.caller.id)
            session.add(row)
        else:
            row = await session.get(McpAgent, args.id)
            if row is None:
                raise ToolError(f"No agent {args.id}")
        row.caller_id, row.name, row.kind, row.app_id = caller_id, args.name.strip(), args.kind, app_id
        row.roles, row.servers = sorted(set(args.roles)), sorted(set(args.servers))
        row.rate_limit, row.enabled = args.rate_limit, args.enabled
        await session.flush()
        agent_id = row.id
    if "directory" in ctx.services:
        await agent_dir.refresh(ctx.services["directory"])
    return {"id": agent_id, "caller_id": caller_id, "saved": True}


@server.tool(callers=CALLERS, roles=ROLES, input_model=AgentEnabled, read_only=False)
async def set_agent_enabled(args: AgentEnabled, ctx: ToolContext) -> dict:
    """Turn an agent on or off. Off: its tokens are refused at once."""
    async with session_scope() as session:
        row = await session.get(McpAgent, args.id)
        if row is None:
            raise ToolError(f"No agent {args.id}")
        row.enabled = args.enabled
    if "directory" in ctx.services:
        await agent_dir.refresh(ctx.services["directory"])
    return {"id": args.id, "enabled": args.enabled}


@server.tool(callers=CALLERS, roles=ROLES, input_model=AgentId, redact=False)
async def preview_agent(args: AgentId, ctx: ToolContext) -> dict:
    """What one agent would see: for each server, the tools it may call now. The same check the guard runs."""
    async with session_scope() as session:
        row = await session.get(McpAgent, args.id)
        if row is None:
            raise ToolError(f"No agent {args.id}")
        caller = agent_dir.to_caller(row)
    gw = ctx.services["gateway"]
    servers = []
    for name in gw.registry.servers:
        tools = await gw.list_tools(caller, name)
        if tools:
            servers.append({"server": name, "tools": [t.name for t in tools]})
    hidden = [t for t in ("radar.decide_approval", "radar.answer_ask", "notify.mark_sent")
              if not any(f"{s['server']}.{x}" == t for s in servers for x in s["tools"])]
    return {"id": args.id, "caller_id": caller.id, "servers": servers,
            "tool_count": sum(len(s["tools"]) for s in servers), "never_allowed": hidden}
