"""The guard. Every tool call from every caller goes through `Gateway.call`:

    known tool → rate limit → tool on and approved → caller kind → role
    → check arguments → run → trim fields → remove PII → audit

Blocked calls are audited too. If the audit row cannot be written, the call
fails: nothing is returned that is not on record.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ValidationError

from app.db import session_scope
from app.mcp.identity import Caller
from app.mcp.pii import redact, redact_text
from app.mcp.projection import project
from app.mcp.ratelimit import RateLimiter
from app.mcp.registry import Registry, ToolContext, ToolSpec
from app.models.mcp import McpCall
from app.settings import Settings

log = logging.getLogger("mcp.guard")


class GuardDenied(Exception):
    """The caller may not use this tool. The message is safe to show."""


class ToolError(Exception):
    """A tool failed in a way the caller should hear about. The message is safe to show."""


@dataclass
class CallResult:
    value: Any
    outcome: str  # ok, denied, error
    message: str = ""


class Gateway:
    def __init__(self, registry: Registry, settings: Settings, services: dict[str, Any] | None = None) -> None:
        self.registry = registry
        self.settings = settings
        self.services = services or {}
        self.limiter = RateLimiter(settings.rate_limit_per_minute)

    def _allowed(self, caller: Caller, spec: ToolSpec) -> tuple[bool, str]:
        if caller.kind not in spec.callers:
            return False, f"{caller.kind.capitalize()} callers may not use this tool"
        if not caller.has_any_role(spec.roles):
            return False, f"Missing role: needs one of {', '.join(sorted(spec.roles))}"
        return True, ""

    async def list_tools(self, caller: Caller, server: str) -> list[ToolSpec]:
        """Tools this caller may use on this server: on, approved and allowed."""
        sdef = self.registry.servers.get(server)
        if sdef is None:
            return []
        out = []
        async with session_scope() as session:
            for spec in sdef.tools.values():
                usable, _ = await self.registry.is_usable(session, spec)
                if usable and self._allowed(caller, spec)[0]:
                    out.append(spec)
        return out

    async def call(self, caller: Caller, server: str, tool: str, arguments: dict[str, Any] | None) -> CallResult:
        started = time.monotonic()
        arguments = dict(arguments or {})
        spec = self.registry.get(server, tool)

        try:
            if spec is None:
                raise GuardDenied(f"Unknown tool {server}.{tool}")
            if not self.limiter.allow(caller.id):
                raise GuardDenied("Too many requests. Try again in a minute")
            async with session_scope() as session:
                usable, why = await self.registry.is_usable(session, spec)
            if not usable:
                raise GuardDenied(why)
            ok, why = self._allowed(caller, spec)
            if not ok:
                raise GuardDenied(why)

            fields = arguments.pop("fields", None)
            if fields is not None and (not isinstance(fields, list) or not all(isinstance(f, str) for f in fields)):
                raise ToolError("fields must be a list of strings")
            try:
                args = spec.input_model.model_validate(arguments)
            except ValidationError as e:
                raise ToolError("Invalid arguments: " + "; ".join(
                    f"{'.'.join(str(p) for p in err['loc']) or 'input'}: {err['msg']}" for err in e.errors()))

            ctx = ToolContext(caller=caller, settings=self.settings, services=self.services)
            value = _plain(await spec.handler(args, ctx))
            value = project(value, fields)
            if spec.redact:
                value = redact(value)
            result = CallResult(value=value, outcome="ok")
        except GuardDenied as e:
            result = CallResult(value=None, outcome="denied", message=str(e))
        except ToolError as e:
            result = CallResult(value=None, outcome="error", message=str(e))
        except Exception:
            log.exception("tool %s.%s failed", server, tool)
            result = CallResult(value=None, outcome="error", message="The tool failed. The error is in the gateway log")

        await self._audit(caller, server, tool, arguments, result, started)
        return result

    async def _audit(self, caller: Caller, server: str, tool: str, arguments: dict[str, Any],
                     result: CallResult, started: float) -> None:
        args_text = redact_text(json.dumps(arguments, default=str, sort_keys=True))
        if len(args_text) > self.settings.audit_args_max_chars:
            args_text = args_text[: self.settings.audit_args_max_chars] + "…"
        async with session_scope() as session:
            session.add(McpCall(
                caller_kind=caller.kind, caller_id=caller.id, server=server, tool=tool,
                outcome=result.outcome, reason=result.message or None, args=args_text,
                duration_ms=int((time.monotonic() - started) * 1000),
            ))


def _plain(value: Any) -> Any:
    """Make a handler's return value JSON-ready."""
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, list):
        return [_plain(v) for v in value]
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    return json.loads(json.dumps(value, default=str))
