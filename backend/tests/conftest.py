"""Test set-up: a separate database (radar_test), migrated from scratch once per
run, with MCP tables emptied before each test."""

import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import create_async_engine

from app.db import set_engine
from app.mcp.identity import Caller
from app.settings import Settings

BACKEND = Path(__file__).resolve().parent.parent
TEST_DB_URL = os.environ.get("TEST_DATABASE_URL", "postgresql+psycopg://radar:radar@localhost:5432/radar_test")

DEV_TOKENS = {
    "t-viewer": {"kind": "human", "id": "viewer@cityholdings.dev", "roles": ["viewer"]},
    "t-admin": {"kind": "human", "id": "admin@cityholdings.dev", "roles": ["viewer", "admin"]},
    "t-radar": {"kind": "agent", "id": "radar", "roles": ["agent"]},
    "t-adapter": {"kind": "service", "id": "adapter", "roles": ["adapter"]},
    "t-approver": {"kind": "human", "id": "pmo@cityholdings.dev", "roles": ["viewer", "approver"]},
    "t-radar-job": {"kind": "service", "id": "radar-job", "roles": ["radar"]},
    "t-notifier": {"kind": "service", "id": "notifier", "roles": ["notifier"]},
}

VIEWER = Caller("human", "viewer@cityholdings.dev", frozenset({"viewer"}))
ADMIN = Caller("human", "admin@cityholdings.dev", frozenset({"viewer", "admin"}))
RADAR = Caller("agent", "radar", frozenset({"agent"}))
ADAPTER = Caller("service", "adapter", frozenset({"adapter"}))
APPROVER = Caller("human", "pmo@cityholdings.dev", frozenset({"viewer", "approver"}))
RADAR_JOB = Caller("service", "radar-job", frozenset({"radar"}))
NOTIFIER = Caller("service", "notifier", frozenset({"notifier"}))


def make_settings(**overrides) -> Settings:
    values = dict(app_env="test", database_url=TEST_DB_URL, dev_tokens=DEV_TOKENS, source_mode="mock",
                  sample_data_path=BACKEND.parent / "design" / "sample-data.json",
                  registry_cache_seconds=0.0, rate_limit_per_minute=1000)
    values.update(overrides)
    return Settings(_env_file=None, **values)


@pytest.fixture(scope="session")
def settings() -> Settings:
    return make_settings()


@pytest.fixture(scope="session", autouse=True)
def migrated_db():
    sync = create_engine(TEST_DB_URL)
    with sync.begin() as conn:
        conn.execute(text("DROP SCHEMA IF EXISTS app CASCADE"))
        conn.execute(text("DROP SCHEMA IF EXISTS mcp CASCADE"))
        conn.execute(text("DROP TABLE IF EXISTS public.alembic_version"))
    sync.dispose()
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    cfg.attributes["database_url"] = TEST_DB_URL
    command.upgrade(cfg, "head")
    yield


@pytest.fixture(scope="session")
async def engine(migrated_db):
    eng = create_async_engine(TEST_DB_URL)
    set_engine(eng)
    yield eng
    await eng.dispose()


@pytest.fixture(autouse=True)
async def clean_mcp(engine):
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE mcp.call, mcp.tool_change, mcp.tool, mcp.server, mcp.person RESTART IDENTITY CASCADE"))
    yield
