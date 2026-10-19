"""MCP endpoints. One MCP server per registry server, mounted at /<name>/mcp.

The MCP SDK handles the protocol (initialize, sessions, Streamable HTTP). A
middleware takes over `tools/list` and `tools/call` and sends them through the
Gateway, so the guard runs on every call and no tool can be reached around it.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from mcp.server.context import CallNext, HandlerResult, ServerMiddleware, ServerRequestContext
from mcp.server.mcpserver import MCPServer
from mcp.shared.exceptions import MCPError
from mcp.types import CallToolResult, ListToolsResult, TextContent, Tool, ToolAnnotations
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.mcp.guard import Gateway
from app.mcp.identity import Caller, TokenResolver, UnknownToken

INVALID_REQUEST = -32600

log = logging.getLogger("mcp.transport")


class GuardMiddleware(ServerMiddleware[Any]):
    def __init__(self, gateway: Gateway, server: str, resolver: TokenResolver, fixed_caller: Caller | None = None):
        self.gateway = gateway
        self.server = server
        self.resolver = resolver
        self.fixed_caller = fixed_caller  # in-process tests only

    def _caller(self, ctx: ServerRequestContext[Any, Any]) -> Caller:
        if self.fixed_caller is not None:
            return self.fixed_caller
        request = ctx.request
        headers = getattr(request, "headers", None)
        try:
            return self.resolver.resolve(headers.get("authorization") if headers else None)
        except UnknownToken as e:
            raise MCPError(code=INVALID_REQUEST, message=str(e)) from e

    async def __call__(self, ctx: ServerRequestContext[Any, Any], call_next: CallNext) -> HandlerResult:
        if ctx.method == "tools/list":
            caller = self._caller(ctx)
            specs = await self.gateway.list_tools(caller, self.server)
            return ListToolsResult(tools=[
                Tool(name=s.name, description=s.description, input_schema=s.input_schema(),
                     annotations=ToolAnnotations(read_only_hint=s.read_only))
                for s in specs
            ])
        if ctx.method == "tools/call":
            caller = self._caller(ctx)
            params = ctx.params or {}
            name = params.get("name")
            if not isinstance(name, str):
                raise MCPError(code=INVALID_REQUEST, message="Tool name is required")
            result = await self.gateway.call(caller, self.server, name, params.get("arguments"))
            if result.outcome != "ok":
                return CallToolResult(content=[TextContent(type="text", text=result.message)], is_error=True)
            structured = result.value if isinstance(result.value, dict) else {"result": result.value}
            return CallToolResult(
                content=[TextContent(type="text", text=json.dumps(result.value, ensure_ascii=False))],
                structured_content=structured,
                is_error=False,
            )
        return await call_next(ctx)


def build_mcp_server(gateway: Gateway, server: str, resolver: TokenResolver,
                     fixed_caller: Caller | None = None) -> MCPServer:
    sdef = gateway.registry.servers[server]
    return MCPServer(
        name=f"city-{server}",
        title=sdef.title,
        description=sdef.description,
        version="0.1.0",
        middleware=[GuardMiddleware(gateway, server, resolver, fixed_caller)],
    )


class RequireToken:
    """HTTP-level check: no valid bearer token, no MCP session at all (401)."""

    def __init__(self, app: ASGIApp, resolver: TokenResolver) -> None:
        self.app = app
        self.resolver = resolver

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            try:
                self.resolver.resolve(Request(scope).headers.get("authorization"))
            except UnknownToken as e:
                client = (scope.get("client") or ("?",))[0]
                log.warning("refused token on %s from %s: %s", scope.get("path"), client, e)
                await JSONResponse({"error": str(e)}, status_code=401,
                                   headers={"WWW-Authenticate": "Bearer"})(scope, receive, send)
                return
        await self.app(scope, receive, send)
