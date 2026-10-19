"""Settings saved in Admin that the worker needs: the LLM for Radar and the
channels for approved drafts. Read through MCP (non-secret values and secret
names); the secret values come from the secret store. If a tool cannot be
used yet (for example still off), the environment values stay in force.
"""

from __future__ import annotations

import logging
import time

from app.adapter.readers import SourceCallError, SourceReader
from app.secretstore import SecretError, SecretStore, resolve
from app.settings import Settings

log = logging.getLogger("radar.runtime")
CACHE_SECONDS = 60.0
_cache: dict[str, tuple[float, Settings]] = {}


async def _cached(key: str, make) -> Settings:
    hit = _cache.get(key)
    if hit and time.monotonic() - hit[0] < CACHE_SECONDS:
        return hit[1]
    value = await make()
    _cache[key] = (time.monotonic(), value)
    return value


async def with_llm(reader: SourceReader, settings: Settings, store: SecretStore) -> Settings:
    return await _cached("llm", lambda: _llm(reader, settings, store))


async def with_channels(reader: SourceReader, settings: Settings, store: SecretStore) -> Settings:
    return await _cached("channels", lambda: _channels(reader, settings, store))


async def _llm(reader: SourceReader, settings: Settings, store: SecretStore) -> Settings:
    try:
        cfg = await reader.call("radar", "get_llm_config")
        if not cfg.get("saved_in_admin"):
            return settings
        key = await resolve(store, cfg.get("api_key_ref", ""))
    except (SourceCallError, SecretError) as e:
        log.warning("LLM settings from Admin not used: %s", e)
        return settings
    return settings.model_copy(update={"llm_base_url": cfg["base_url"], "llm_model": cfg["model"], "llm_api_key": key})


async def _channels(reader: SourceReader, settings: Settings, store: SecretStore) -> Settings:
    try:
        ch = await reader.call("notify", "get_channels")
        teams, email = ch["teams"], ch["email"]
        webhook = await resolve(store, teams.get("webhook_ref", ""))
        password = await resolve(store, email.get("password_ref", ""))
    except (SourceCallError, SecretError) as e:
        log.warning("Channel settings from Admin not used: %s", e)
        return settings
    return settings.model_copy(update={
        "teams_webhook_url": webhook, "smtp_host": email["smtp_host"], "smtp_port": email["smtp_port"],
        "smtp_user": email["username"], "smtp_password": password, "smtp_from": email["sender"],
        "notify_email_to": email["recipients"]})
