"""MCP registry and audit log (schema `mcp`).

Every server and tool the gateway exposes has a row here. Tools start `off` and
stay off until their owner turns them on. If a tool's description or input schema
changes in code, the tool moves to `review` and stays unusable until the owner
approves the change.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

SCHEMA = "mcp"

TOOL_STATUSES = ("off", "on", "review")


class McpServer(Base):
    __tablename__ = "server"
    __table_args__ = {"schema": SCHEMA}

    name: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    owner: Mapped[str] = mapped_column(String(200))
    direction: Mapped[str] = mapped_column(String(8))  # "in" (source) or "out" (app)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class McpTool(Base):
    __tablename__ = "tool"
    __table_args__ = (UniqueConstraint("server", "name"), {"schema": SCHEMA})

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    server: Mapped[str] = mapped_column(ForeignKey(f"{SCHEMA}.server.name"))
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text)
    input_schema: Mapped[dict[str, Any]] = mapped_column(JSON)
    callers: Mapped[list[str]] = mapped_column(JSON)  # allowed caller kinds
    roles: Mapped[list[str]] = mapped_column(JSON)  # any of these roles; empty = any role
    read_only: Mapped[bool] = mapped_column(Boolean, default=True)
    # Hash of the approved description + schema + access rules. A different hash in code means review.
    approved_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    code_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(8), default="off")
    status_changed_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    status_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class McpToolChange(Base):
    """A change to a tool found at start-up, waiting for the owner to approve it."""

    __tablename__ = "tool_change"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tool_id: Mapped[int] = mapped_column(ForeignKey(f"{SCHEMA}.tool.id"))
    old_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    new_hash: Mapped[str] = mapped_column(String(64))
    diff: Mapped[dict[str, Any]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(10), default="pending")  # pending, approved, rejected
    decided_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class McpCall(Base):
    """Audit log: one row for every tool call, allowed or blocked."""

    __tablename__ = "call"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    caller_kind: Mapped[str] = mapped_column(String(10))
    caller_id: Mapped[str] = mapped_column(String(200), index=True)
    server: Mapped[str] = mapped_column(String(64))
    tool: Mapped[str] = mapped_column(String(100))
    outcome: Mapped[str] = mapped_column(String(10))  # ok, denied, error
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    args: Mapped[str | None] = mapped_column(Text, nullable=True)  # PII removed, shortened
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
