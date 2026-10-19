"""How the adapter reaches the source servers. Always through the gateway:
over MCP/HTTP in production (the worker container), or in-process in tests.
Either way the guard checks and audits every call."""

from __future__ import annotations

from contextlib import AsyncExitStack
from typing import Any, Protocol

import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

from app.mcp.guard import Gateway
from app.mcp.identity import Caller


class SourceCallError(Exception):
    """A source server answered with an error. The message is safe to log and show."""


class SourceReader(Protocol):
    async def call(self, server: str, tool: str, args: dict[str, Any] | None = None) -> Any: ...


class GatewayReader:
    """In-process: calls Gateway.call directly as the given service caller."""

    def __init__(self, gateway: Gateway, caller: Caller) -> None:
        self.gateway = gateway
        self.caller = caller

    async def call(self, server: str, tool: str, args: dict[str, Any] | None = None) -> Any:
        r = await self.gateway.call(self.caller, server, tool, args or {})
        if r.outcome != "ok":
            raise SourceCallError(r.message)
        return r.value


class McpHttpReader:
    """Over MCP Streamable HTTP with a service token. One session per server per run."""

    def __init__(self, base_url: str, token: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self._stack = AsyncExitStack()
        self._clients: dict[str, Client] = {}
        self._http: httpx2.AsyncClient | None = None

    async def __aenter__(self) -> McpHttpReader:
        self._http = await self._stack.enter_async_context(
            httpx2.AsyncClient(headers={"Authorization": f"Bearer {self.token}"}, timeout=120))
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self._stack.aclose()

    async def _client(self, server: str) -> Client:
        if server not in self._clients:
            transport = streamable_http_client(f"{self.base_url}/{server}/mcp", http_client=self._http)
            self._clients[server] = await self._stack.enter_async_context(Client(transport))
        return self._clients[server]

    async def call(self, server: str, tool: str, args: dict[str, Any] | None = None) -> Any:
        client = await self._client(server)
        r = await client.call_tool(tool, args or {})
        if r.is_error:
            raise SourceCallError(r.content[0].text if r.content else "error")
        sc = r.structured_content or {}
        return sc["result"] if set(sc) == {"result"} else sc
