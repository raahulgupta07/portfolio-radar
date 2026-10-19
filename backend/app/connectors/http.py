"""HTTP client for source trackers that can only read.

There is no method for POST, PUT, PATCH or DELETE, and a request hook refuses
anything but GET or HEAD in case someone reaches the inner client. This is how
"never write to JIRA, OpenProject or Multica" is enforced in code.
"""

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from app.connectors.base import SourceUnavailable

READ_METHODS = frozenset({"GET", "HEAD"})
RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
MAX_RETRY_AFTER = 60.0  # seconds; a tracker cannot park the nightly sync
MAX_BODY = 20_000_000  # bytes per answer


class ReadOnlyViolation(RuntimeError):
    pass


async def _only_read(request: httpx.Request) -> None:
    if request.method.upper() not in READ_METHODS:
        raise ReadOnlyViolation(f"Blocked {request.method} {request.url.path}: source access is read-only")


class ReadOnlyHttpClient:
    def __init__(
        self,
        source_name: str,
        base_url: str,
        headers: dict[str, str] | None = None,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        max_retries: int = 3,
        backoff_seconds: float = 1.0,
        timeout_seconds: float = 30.0,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.source_name = source_name
        self.max_retries = max_retries
        self.backoff_seconds = backoff_seconds
        self._sleep = sleep
        self._client = httpx.AsyncClient(
            base_url=base_url, headers=headers or {}, transport=transport, timeout=timeout_seconds,
            event_hooks={"request": [_only_read]},
        )

    async def get_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        for attempt in range(self.max_retries + 1):
            last_try = attempt == self.max_retries
            try:
                resp = await self._client.get(path, params=params)
            except httpx.TransportError as e:
                if last_try:
                    raise SourceUnavailable(f"{self.source_name}: cannot connect ({type(e).__name__})") from e
                await self._sleep(self._delay(attempt + 1, None))
                continue
            if resp.status_code in RETRY_STATUSES and not last_try:
                await self._sleep(self._delay(attempt + 1, resp))
                continue
            if resp.status_code in (401, 403):
                raise SourceUnavailable(f"{self.source_name}: {resp.status_code} access denied (check the read-only token)")
            if resp.status_code >= 400:
                raise SourceUnavailable(f"{self.source_name}: HTTP {resp.status_code} for {path}")
            if len(resp.content) > MAX_BODY:
                raise SourceUnavailable(f"{self.source_name}: answer too large for {path}")
            try:
                return resp.json()
            except ValueError as e:
                raise SourceUnavailable(f"{self.source_name}: not JSON from {path}") from e
        raise AssertionError("unreachable")

    def _delay(self, attempt: int, resp: httpx.Response | None) -> float:
        if resp is not None and resp.status_code == 429:
            retry_after = resp.headers.get("retry-after", "")
            if retry_after.isdigit():
                return min(float(retry_after), MAX_RETRY_AFTER)
        return self.backoff_seconds * (2 ** (attempt - 1))

    async def aclose(self) -> None:
        await self._client.aclose()
