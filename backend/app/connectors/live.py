"""Live connectors, built from what an admin saved in Admin → Connections.

A LiveConnector stands in for one source. On each call it uses the source's
saved address, sign-in, token (from the secret store) and confirmed field
mapping. It rebuilds the real connector when any of those change, and checks
for changes at most every `CONFIG_SECONDS`, so the gateway never needs a
restart after an admin edits a connection.
"""

from __future__ import annotations

import hashlib
import time
from collections.abc import Callable
from typing import Any

import httpx

from app.connectors import fields as fm
from app.connectors import jira, multica, openproject
from app.connectors.base import SourceUnavailable
from app.connectors.http import ReadOnlyHttpClient
from app.db import session_scope
from app.models.app import Source
from app.secretstore import SecretError, SecretStore, resolve
from app.settings import Settings

CONFIG_SECONDS = 60.0
WHERE = "Admin → Connections → {name}"


class LiveConnector:
    def __init__(self, source_id: str, name: str, settings: Settings, store: SecretStore, *,
                 transport: httpx.AsyncBaseTransport | None = None, clock: Callable[[], float] = time.monotonic) -> None:
        self.source_id = source_id
        self.name = name
        self.settings = settings
        self.store = store
        self.transport = transport  # tests pass recorded responses here
        self.clock = clock
        self._inner: Any = None
        self._fingerprint = ""
        self._checked = -1e9
        self._confirmed = False

    def _where(self) -> str:
        return WHERE.format(name=self.name)

    async def _config(self) -> tuple[Source, fm.FieldMapping | None]:
        async with session_scope() as session:
            row = await session.get(Source, self.source_id)
            mapping = await fm.load(session, self.source_id)
            if row is not None:
                session.expunge(row)
        if row is None:
            raise SourceUnavailable(f"{self.name}: no such source")
        return row, mapping

    async def connector(self, needs_mapping: bool = True) -> Any:
        """The real connector. Listing projects works before the field mapping is confirmed, so an admin can
        check the address and token first; reading project fields does not."""
        if self._inner is None or self.clock() - self._checked >= CONFIG_SECONDS:
            await self._load()
        if needs_mapping and not self._confirmed:
            raise SourceUnavailable(f"{self.name}: field mapping not confirmed yet ({self._where()} → field mapping)")
        return self._inner

    async def _load(self) -> None:
        if self.source_id not in fm.MODELS:
            raise SourceUnavailable(f"{self.name}: the live connector is not built yet (its API is needed). "
                                    "Use SOURCE_MODE=mock or turn this source off in " + self._where())
        row, mapping = await self._config()
        if not row.base_url:
            raise SourceUnavailable(f"{self.name}: no address set ({self._where()})")
        if not row.secret_ref:
            raise SourceUnavailable(f"{self.name}: no read token set ({self._where()})")
        if mapping is None:
            raise SourceUnavailable(f"{self.name}: no field mapping")
        try:
            token = await resolve(self.store, row.secret_ref)
        except SecretError as e:
            raise SourceUnavailable(f"{self.name}: {e}") from e
        parts = [row.base_url, row.flavor, row.auth_method, row.account, token, repr(sorted(mapping.fields.items()))]
        fingerprint = hashlib.sha256("\x00".join(parts).encode()).hexdigest()
        if fingerprint != self._fingerprint or self._inner is None:
            await self.aclose()
            self._inner = self._build(row, mapping, token)
            self._fingerprint = fingerprint
        self._confirmed = mapping.confirmed
        self._checked = self.clock()

    def _build(self, row: Source, mapping: fm.FieldMapping, token: str) -> Any:
        aspirations = list(self.settings.strategy_aspirations)
        if self.source_id == "jira":
            flavor = row.flavor or "cloud"
            client = ReadOnlyHttpClient(self.name, row.base_url, jira.auth_headers(flavor, row.account, token),
                                        transport=self.transport)
            return jira.JiraConnector(client, flavor=flavor, base_url=row.base_url,
                                      fields=fm.JiraFields.model_validate(mapping.fields), aspirations=aspirations)
        if self.source_id == "multica":
            client = ReadOnlyHttpClient(self.name, row.base_url, multica.auth_headers(token), transport=self.transport)
            return multica.MulticaConnector(client, base_url=row.base_url, fields=fm.MulticaFields.model_validate(mapping.fields))
        client = ReadOnlyHttpClient(self.name, row.base_url, openproject.auth_headers(token), transport=self.transport)
        return openproject.OpenProjectConnector(client, base_url=row.base_url, aspirations=aspirations,
                                                fields=fm.OpenProjectFields.model_validate(mapping.fields))

    def invalidate(self) -> None:
        """Re-read the set-up on the next call (after an admin saves a change)."""
        self._checked = -1e9

    async def aclose(self) -> None:
        if self._inner is not None:
            await self._inner.client.aclose()
            self._inner = None

    def __getattr__(self, method: str) -> Any:
        if method.startswith("_") or method not in {"list_projects", "get_project", "get_milestones", "get_sprints",
                                                    "get_task_counts", "get_links", "get_risks"}:
            raise AttributeError(method)

        async def call(*args: Any, **kwargs: Any) -> Any:
            inner = await self.connector(needs_mapping=method != "list_projects")
            try:
                return await getattr(inner, method)(*args, **kwargs)
            except (KeyError, TypeError, ValueError) as e:
                raise SourceUnavailable(f"{self.name}: unexpected answer from the tracker ({type(e).__name__}: {e})") from e
        return call
