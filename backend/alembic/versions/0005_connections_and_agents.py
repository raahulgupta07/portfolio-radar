"""connections set up in Admin: source details, agents

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-19 12:00:00
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '0005'
down_revision: str | None = '0004'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('source', sa.Column('flavor', sa.String(16), server_default='', nullable=False), schema='app')
    op.add_column('source', sa.Column('auth_method', sa.String(32), server_default='', nullable=False), schema='app')
    op.add_column('source', sa.Column('account', sa.String(200), server_default='', nullable=False), schema='app')
    op.add_column('source', sa.Column('unmapped_statuses', sa.JSON(), server_default='[]', nullable=False), schema='app')
    # Secret names become references: jira-read-token -> kv://jira-read-token
    op.execute("UPDATE app.source SET secret_ref = 'kv://' || secret_ref "
               "WHERE secret_ref <> '' AND secret_ref NOT LIKE '%://%'")
    op.create_table(
        'agent',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('caller_id', sa.String(64), nullable=False, unique=True),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('kind', sa.String(10), nullable=False),
        sa.Column('app_id', sa.String(36), nullable=False, unique=True),
        sa.Column('roles', sa.JSON(), nullable=False),
        sa.Column('servers', sa.JSON(), nullable=False),
        sa.Column('rate_limit', sa.Integer(), nullable=False, server_default='120'),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_by', sa.String(200), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema='mcp',
    )


def downgrade() -> None:
    op.drop_table('agent', schema='mcp')
    for col in ('unmapped_statuses', 'account', 'auth_method', 'flavor'):
        op.drop_column('source', col, schema='app')
