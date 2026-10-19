"""Secret store. The app keeps only secret *names*; the values live here.

A secret reference is one of:
- `kv://jira-read-token`  a secret in the store (Azure Key Vault in production)
- `env://LLM_API_KEY`     an environment variable (for set-ups that already use them)

Admins paste a secret once in the Admin page. It goes straight to the store and
is never shown, logged or returned again; the page only shows its name.

Stores:
- keyvault: Azure Key Vault, signed in with the container's managed identity
- local:    a JSON file readable only by its owner. Dev and test only
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from pathlib import Path
from typing import Protocol

from app.settings import Settings

KV_REF = re.compile(r"^kv://([a-z0-9][a-z0-9-]{0,99})$")
ENV_REF = re.compile(r"^env://([A-Z][A-Z0-9_]{0,99})$")
REF_PATTERN = r"^$|^kv://[a-z0-9][a-z0-9-]{0,99}$|^env://[A-Z][A-Z0-9_]{0,99}$"


class SecretError(Exception):
    """The message is safe to show. It never contains a secret value."""


def kv_name(ref: str) -> str:
    m = KV_REF.match(ref)
    if not m:
        raise SecretError("Secret names look like kv://jira-read-token (lower case, digits and dashes)")
    return m.group(1)


class SecretStore(Protocol):
    kind: str
    writable: bool

    async def get(self, name: str) -> str | None: ...
    async def set(self, name: str, value: str) -> None: ...


class LocalStore:
    """Dev and test only: a JSON file next to the backend, mode 600, not in git."""

    kind = "local"
    writable = True

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._lock = asyncio.Lock()

    def _read(self) -> dict[str, str]:
        try:
            return json.loads(self.path.read_text())
        except FileNotFoundError:
            return {}

    async def get(self, name: str) -> str | None:
        return self._read().get(name)

    async def set(self, name: str, value: str) -> None:
        async with self._lock:
            data = self._read()
            data[name] = value
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w") as f:
                json.dump(data, f)
            os.replace(tmp, self.path)


class KeyVaultStore:
    """Azure Key Vault. Needs `pip install .[keyvault]` and a managed identity
    with get and set rights on secrets."""

    kind = "keyvault"
    writable = True

    def __init__(self, url: str) -> None:
        if not url:
            raise SecretError("SECRET_STORE=keyvault needs KEY_VAULT_URL")
        try:
            from azure.identity.aio import DefaultAzureCredential
            from azure.keyvault.secrets.aio import SecretClient
        except ImportError as e:  # pragma: no cover - optional dependency
            raise SecretError("Key Vault support is not installed (pip install .[keyvault])") from e
        self._client = SecretClient(vault_url=url, credential=DefaultAzureCredential())

    async def get(self, name: str) -> str | None:  # pragma: no cover - needs Azure
        from azure.core.exceptions import ResourceNotFoundError

        try:
            return (await self._client.get_secret(name)).value
        except ResourceNotFoundError:
            return None

    async def set(self, name: str, value: str) -> None:  # pragma: no cover - needs Azure
        await self._client.set_secret(name, value)


def build_secret_store(settings: Settings) -> SecretStore:
    if settings.secret_store == "keyvault":
        return KeyVaultStore(settings.key_vault_url)
    if settings.app_env == "prod":
        raise SecretError("Production needs SECRET_STORE=keyvault. The local file store is for dev and test only")
    return LocalStore(settings.secret_store_path)


async def resolve(store: SecretStore, ref: str) -> str:
    """The secret's value, or "" when the reference is empty or the secret is not set."""
    if not ref:
        return ""
    if m := ENV_REF.match(ref):
        return os.environ.get(m.group(1), "")
    return await store.get(kv_name(ref)) or ""


async def is_set(store: SecretStore, ref: str) -> bool:
    try:
        return bool(await resolve(store, ref))
    except SecretError:
        return False
