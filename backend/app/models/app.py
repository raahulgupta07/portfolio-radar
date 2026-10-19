"""Portfolio data model (schema `app`), from docs/PRD.md → "Data model".

The adapter writes these tables. The gateway's app servers read them. Nothing
else connects to the database.
"""

from datetime import date, datetime
from typing import Any

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

SCHEMA = "app"


def _fk(table: str) -> str:
    return f"{SCHEMA}.{table}.id"


class Source(Base):
    __tablename__ = "source"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[str] = mapped_column(String(32), primary_key=True)  # jira, openproject, multica
    type: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(100))
    team: Mapped[str] = mapped_column(String(100), default="")
    base_url: Mapped[str] = mapped_column(String(500), default="")
    secret_ref: Mapped[str] = mapped_column(String(200), default="")  # name in the secret store, never the secret
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_good_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_status: Mapped[str] = mapped_column(String(16), default="never")  # never, ok, failed
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)


class Prefix(Base):
    __tablename__ = "prefix"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    value: Mapped[str] = mapped_column(String(50), unique=True)
    description: Mapped[str] = mapped_column(String(200), default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Project(Base):
    __tablename__ = "project"
    __table_args__ = (UniqueConstraint("source_id", "source_key"), {"schema": SCHEMA})

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(64), index=True)
    prefix: Mapped[str] = mapped_column(String(50))
    name: Mapped[str] = mapped_column(String(300))
    team: Mapped[str] = mapped_column(String(100), default="")
    owner: Mapped[str | None] = mapped_column(String(200), nullable=True)
    status: Mapped[str] = mapped_column(String(20))  # Not started, In progress, Done, On hold
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    percent_done: Mapped[int | None] = mapped_column(Integer, nullable=True)
    health: Mapped[str | None] = mapped_column(String(12), nullable=True)  # on_track, at_risk, off_track, done
    health_reasons: Mapped[list[str]] = mapped_column(JSON, default=list)
    status_raw: Mapped[str | None] = mapped_column(String(60), nullable=True)  # the tracker's own status
    strategy_tag: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source_id: Mapped[str] = mapped_column(ForeignKey(f"{SCHEMA}.source.id"))
    source_key: Mapped[str] = mapped_column(String(100))
    source_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Milestone(Base):
    __tablename__ = "milestone"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey(_fk("project"), ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(300))
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="open")
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Sprint(Base):
    __tablename__ = "sprint"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey(_fk("project"), ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    goal: Mapped[str | None] = mapped_column(Text, nullable=True)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    state: Mapped[str] = mapped_column(String(20), default="active")


class TaskSummary(Base):
    __tablename__ = "task_summary"
    __table_args__ = {"schema": SCHEMA}

    project_id: Mapped[int] = mapped_column(ForeignKey(_fk("project"), ondelete="CASCADE"), primary_key=True)
    todo: Mapped[int] = mapped_column(Integer, default=0)
    in_progress: Mapped[int] = mapped_column(Integer, default=0)
    done: Mapped[int] = mapped_column(Integer, default=0)
    total: Mapped[int] = mapped_column(Integer, default=0)


class Dependency(Base):
    __tablename__ = "dependency"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    from_project_id: Mapped[int] = mapped_column(ForeignKey(_fk("project"), ondelete="CASCADE"))
    to_project_id: Mapped[int] = mapped_column(ForeignKey(_fk("project"), ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(20), default="blocks")
    origin: Mapped[str] = mapped_column(String(20), default="tracker")  # tracker, pmo


class Risk(Base):
    __tablename__ = "risk"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey(_fk("project"), ondelete="CASCADE"), nullable=True)
    title: Mapped[str] = mapped_column(String(300))
    likelihood: Mapped[str] = mapped_column(String(10))
    impact: Mapped[str] = mapped_column(String(10))
    owner: Mapped[str | None] = mapped_column(String(200), nullable=True)
    origin: Mapped[str] = mapped_column(String(20), default="tracker")  # tracker, radar, pmo
    review_date: Mapped[date | None] = mapped_column(Date, nullable=True)


class Snapshot(Base):
    __tablename__ = "snapshot"
    __table_args__ = (UniqueConstraint("date", "project_id"), {"schema": SCHEMA})

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey(_fk("project"), ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(20))
    health: Mapped[str | None] = mapped_column(String(12), nullable=True)
    percent_done: Mapped[int | None] = mapped_column(Integer, nullable=True)


class SyncRun(Base):
    __tablename__ = "sync_run"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[str] = mapped_column(ForeignKey(f"{SCHEMA}.source.id"))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    projects_read: Mapped[int] = mapped_column(Integer, default=0)
    errors_json: Mapped[list[Any]] = mapped_column(JSON, default=list)
    result: Mapped[str] = mapped_column(String(16), default="running")  # running, ok, failed


class NonCompliant(Base):
    __tablename__ = "non_compliant"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[str] = mapped_column(ForeignKey(f"{SCHEMA}.source.id"))
    name_in_tracker: Mapped[str] = mapped_column(String(300))
    reason: Mapped[str] = mapped_column(String(200))
    seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AgentRun(Base):
    __tablename__ = "agent_run"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    projects_checked: Mapped[int] = mapped_column(Integer, default=0)
    findings: Mapped[int] = mapped_column(Integer, default=0)
    drafts: Mapped[int] = mapped_column(Integer, default=0)


class Finding(Base):
    __tablename__ = "finding"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey(_fk("agent_run")))
    project_id: Mapped[int | None] = mapped_column(ForeignKey(_fk("project"), ondelete="CASCADE"), nullable=True)
    type: Mapped[str] = mapped_column(String(16))  # health, stale, data, slipping, sync, change
    severity: Mapped[str] = mapped_column(String(10))
    text: Mapped[str] = mapped_column(Text)
    evidence_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    dismissed_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    dismissed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RadarMessage(Base):
    __tablename__ = "radar_message"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(String(200), index=True)
    kind: Mapped[str] = mapped_column(String(16))  # radar, me, ask, approval, pill, health, findings, dep
    body: Mapped[str] = mapped_column(Text, default="")
    mood: Mapped[str | None] = mapped_column(String(16), nullable=True)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Approval(Base):
    __tablename__ = "approval"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(10))  # digest, nudge
    draft_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(10), default="pending")  # pending, approved, rejected
    created_by: Mapped[str] = mapped_column(String(200))
    decided_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RadarMemory(Base):
    __tablename__ = "radar_memory"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    text: Mapped[str] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
