"""Alembic environment. Uses DATABASE_URL from app settings and creates the
`app` and `mcp` schemas before running migrations."""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, text

import app.models  # noqa: F401  (registers every table)
from app.db import SCHEMAS, Base
from app.settings import get_settings

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_online() -> None:
    url = config.attributes.get("database_url") or get_settings().database_url
    engine = create_engine(url)
    with engine.begin() as conn:
        for schema in SCHEMAS:
            conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))
    with engine.connect() as conn:
        context.configure(connection=conn, target_metadata=target_metadata, include_schemas=True,
                          compare_type=True)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    raise SystemExit("Offline migrations are not supported; run against a database.")
run_migrations_online()
