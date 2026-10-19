"""Outside services an admin sets up in the app: City SSO, the LLM for Radar,
Microsoft Teams and email. Stored in app.setting under `integration.<name>`.

Until an admin saves one, the environment variables give the values, so
existing set-ups keep working. Secrets are references (kv://…), never values.
"""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.app import Setting
from app.secretstore import ref_pattern
from app.settings import Settings

Role = Literal["viewer", "approver", "admin"]
URL = r"^$|^https://[^\s/$.?#][^\s]*$"  # https only: keys travel with every request
GUID = r"^$|^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"


class GroupRole(BaseModel):
    group_id: str = Field(pattern=GUID[4:], description="Entra group object ID")
    name: str = Field("", max_length=100)
    roles: list[Role] = Field(min_length=1)


class SsoConfig(BaseModel):
    tenant_id: str = Field("", pattern=GUID)
    audience: str = Field("", max_length=200, description="The gateway's app ID URI, e.g. api://city-mcp-gateway")
    default_roles: list[Role] = Field(default_factory=lambda: ["viewer"])
    groups: list[GroupRole] = Field(default_factory=list, max_length=50)
    user_apps: list[str] = Field(default_factory=list, max_length=10,
                                 description="Other app registrations people sign in through (the web app is always allowed)")

    @field_validator("user_apps")
    @classmethod
    def _guids(cls, v: list[str]) -> list[str]:
        if any(not re.fullmatch(GUID[4:], x) for x in v):
            raise ValueError("user_apps must be app (client) IDs")
        return v

    @field_validator("groups")
    @classmethod
    def _one_admin(cls, v: list[GroupRole]) -> list[GroupRole]:
        if v and not any("admin" in g.roles for g in v):
            raise ValueError("at least one group must have the admin role, or nobody can reach Admin")
        return v

    def ready(self) -> bool:
        return bool(self.tenant_id and self.audience)


class LlmConfig(BaseModel):
    provider: Literal["citygpt", "azure_openai", "claude", "other"] = "citygpt"
    base_url: str = Field("", pattern=URL, max_length=500)
    model: str = Field("", max_length=100)
    api_key_ref: str = Field("", pattern=ref_pattern("LLM_API_KEY"))

    def ready(self) -> bool:
        return bool(self.base_url and self.model)


class TeamsConfig(BaseModel):
    webhook_ref: str = Field("", pattern=ref_pattern("TEAMS_WEBHOOK_URL"), description="The webhook URL is a secret")
    channel: str = Field("", max_length=100)
    # Two-way chat: people message Radar in Teams (docs/teams-bot.md). Empty = chat in the app only.
    bot_app_id: str = Field("", pattern=GUID, description="The Azure Bot's Microsoft app ID")
    bot_password_ref: str = Field("", pattern=ref_pattern("TEAMS_BOT_PASSWORD"), description="The bot app's client secret, by name")

    def ready(self) -> bool:
        return bool(self.webhook_ref)

    def bot_ready(self) -> bool:
        return bool(self.bot_app_id and self.bot_password_ref)


class EmailConfig(BaseModel):
    smtp_host: str = Field("", max_length=200, pattern=r"^$|^[A-Za-z0-9.-]+$")
    smtp_port: int = Field(587, ge=1, le=65535)
    username: str = Field("", max_length=200)
    password_ref: str = Field("", pattern=ref_pattern("SMTP_PASSWORD"))
    sender: str = Field("portfolio-radar@cityholdings.com.mm", max_length=200)
    recipients: list[str] = Field(default_factory=list, max_length=50)

    @field_validator("recipients")
    @classmethod
    def _emails(cls, v: list[str]) -> list[str]:
        out = [x.strip() for x in v if x.strip()]
        bad = [x for x in out if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", x)]
        if bad:
            raise ValueError(f"not an email address: {bad[0]}")
        return out

    def ready(self) -> bool:
        return bool(self.smtp_host and self.recipients)


MODELS: dict[str, type[BaseModel]] = {"sso": SsoConfig, "llm": LlmConfig, "teams": TeamsConfig, "email": EmailConfig}
Name = Literal["sso", "llm", "teams", "email"]


def from_env(name: str, env: Settings) -> BaseModel:
    """What the environment variables say, for installs that set nothing in Admin yet."""
    if name == "sso":
        groups = [GroupRole.model_construct(group_id=g, name="", roles=list(r)) for g, r in env.entra_group_roles.items() if r]
        return SsoConfig.model_construct(tenant_id=env.entra_tenant_id, audience=env.entra_audience,
                                         default_roles=list(env.entra_default_roles), groups=groups)
    if name == "llm":
        # Operator-set environment: shown as is, even an http address (Admin only accepts https).
        return LlmConfig.model_construct(provider="citygpt", base_url=env.llm_base_url, model=env.llm_model,
                         api_key_ref="env://LLM_API_KEY" if env.llm_api_key else "")
    if name == "teams":
        return TeamsConfig(webhook_ref="env://TEAMS_WEBHOOK_URL" if env.teams_webhook_url else "",
                           bot_app_id=env.teams_bot_app_id,
                           bot_password_ref="env://TEAMS_BOT_PASSWORD" if env.teams_bot_password else "")
    if name == "email":
        return EmailConfig(smtp_host=env.smtp_host, smtp_port=env.smtp_port, username=env.smtp_user,
                           password_ref="env://SMTP_PASSWORD" if env.smtp_password else "",
                           sender=env.smtp_from, recipients=list(env.notify_email_to))
    raise KeyError(name)


async def load(session: AsyncSession, name: str, env: Settings) -> tuple[BaseModel, bool]:
    """The config and whether it was saved in Admin (False = from the environment)."""
    row = await session.get(Setting, f"integration.{name}")
    if row is None:
        return from_env(name, env), False
    return MODELS[name].model_validate(row.value), True


async def save(session: AsyncSession, name: str, config: dict[str, Any], by: str) -> BaseModel:
    model = MODELS[name].model_validate(config)
    key = f"integration.{name}"
    row = await session.get(Setting, key)
    value = model.model_dump(mode="json")
    if row is None:
        session.add(Setting(key=key, value=value, updated_by=by))
    else:
        row.value, row.updated_by = value, by
    return model
