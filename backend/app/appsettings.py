"""Settings admins change in the app (Admin page): sync schedule, Radar rules,
alerts. Stored in app.setting; the environment gives the defaults."""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.health import Thresholds
from app.models.app import Setting
from app.settings import Settings


class Alerts(BaseModel):
    off_track: bool = True
    milestone_overdue: bool = True
    sync_failed: bool = True
    digest_ready: bool = True
    no_update: bool = False


class Channels(BaseModel):
    in_app: bool = True
    email: bool = True
    teams: bool = True


class AdminSettings(BaseModel):
    sync_time: str = Field("02:00", description="Daily sync time, HH:MM")
    timezone: str = "Asia/Yangon"
    radar_on: bool = True
    stale_days: int = Field(14, ge=1, le=90)
    slipping_window_days: int = Field(7, ge=1, le=60)
    overdue_days: int = Field(3, ge=0, le=60)
    behind_points: int = Field(15, ge=1, le=100)
    approvers_group: str = "Portfolio Admins"
    digest_day: str = "Fri"
    digest_time: str = "16:00"
    digest_recipients: str = "Steering Committee, CTO"
    alerts: Alerts = Field(default_factory=Alerts)
    channels: Channels = Field(default_factory=Channels)

    @field_validator("sync_time", "digest_time")
    @classmethod
    def _hhmm(cls, v: str) -> str:
        if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", v):
            raise ValueError("use HH:MM, for example 02:00")
        return v

    @field_validator("digest_day")
    @classmethod
    def _day(cls, v: str) -> str:
        days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        if v not in days:
            raise ValueError(f"use one of {', '.join(days)}")
        return v

    def thresholds(self) -> Thresholds:
        return Thresholds(self.overdue_days, self.behind_points, self.slipping_window_days)

    def sync_cron(self) -> str:
        h, m = self.sync_time.split(":")
        return f"{int(m)} {int(h)} * * *"


def defaults(env: Settings) -> AdminSettings:
    h_m = env.sync_cron.split()
    sync_time = f"{int(h_m[1]):02d}:{int(h_m[0]):02d}" if len(h_m) == 5 and h_m[0].isdigit() and h_m[1].isdigit() else "02:00"
    return AdminSettings(sync_time=sync_time, timezone=env.timezone, stale_days=env.stale_days,
                         slipping_window_days=env.health_milestone_window_days, overdue_days=env.health_overdue_days,
                         behind_points=env.health_behind_points)


async def load(session: AsyncSession, env: Settings) -> AdminSettings:
    data: dict[str, Any] = defaults(env).model_dump()
    for row in (await session.scalars(select(Setting))).all():
        if row.key in data:
            data[row.key] = row.value
    return AdminSettings.model_validate(data)


async def update(session: AsyncSession, env: Settings, changes: dict[str, Any], by: str) -> AdminSettings:
    current = (await load(session, env)).model_dump()
    unknown = set(changes) - set(current)
    if unknown:
        raise ValueError(f"Unknown settings: {', '.join(sorted(unknown))}")
    merged = AdminSettings.model_validate({**current, **changes})  # validates everything
    for key in changes:
        value = merged.model_dump()[key]
        row = await session.get(Setting, key)
        if row is None:
            session.add(Setting(key=key, value=value, updated_by=by))
        else:
            row.value, row.updated_by = value, by
    return merged
