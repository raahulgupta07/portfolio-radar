"""How the worker's jobs sign in to the gateway.

- token (dev, test, docker compose): fixed tokens from the environment, matched by DEV_TOKENS.
- managed_identity (Azure): each job has its own user-assigned managed identity and asks
  Entra ID for an access token to the gateway (GATEWAY_SCOPE). The gateway knows these
  identities by their client IDs (ENTRA_APPS), so the nightly sync can only do what the
  adapter may do, the notifier only what the notifier may do, and so on. No secret is stored.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Literal

from app.settings import Settings

Job = Literal["adapter", "radar_job", "radar", "notifier"]
JOBS: tuple[Job, ...] = ("adapter", "radar_job", "radar", "notifier")


def _default_credential(client_id: str) -> Any:  # pragma: no cover - needs Azure
    from azure.identity.aio import ManagedIdentityCredential

    return ManagedIdentityCredential(client_id=client_id)


class ServiceTokens:
    def __init__(self, settings: Settings, credential: Callable[[str], Any] = _default_credential) -> None:
        self.settings = settings
        self._make = credential
        self._creds: dict[str, Any] = {}  # one per identity; each caches its token until shortly before expiry

    def _static(self, job: Job) -> str:
        s = self.settings
        return {"adapter": s.adapter_token, "radar_job": s.radar_token, "radar": s.radar_agent_token,
                "notifier": s.notifier_token}[job]

    def client_id(self, job: Job) -> str:
        s = self.settings
        return {"adapter": s.adapter_client_id, "radar_job": s.radar_job_client_id, "radar": s.radar_agent_client_id,
                "notifier": s.notifier_client_id}[job]

    async def get(self, job: Job) -> str:
        if self.settings.service_auth == "token":
            return self._static(job)
        client_id = self.client_id(job)
        if not client_id or not self.settings.gateway_scope:
            raise RuntimeError(f"SERVICE_AUTH=managed_identity needs GATEWAY_SCOPE and the {job} identity's client ID")
        cred = self._creds.get(client_id)
        if cred is None:
            cred = self._creds[client_id] = self._make(client_id)
        return (await cred.get_token(self.settings.gateway_scope)).token

    async def aclose(self) -> None:
        for cred in self._creds.values():
            close = getattr(cred, "close", None)
            if close is not None:
                await close()
        self._creds.clear()
