"""raw pull archive: what each source answered, per day

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-21 12:00:00
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '0009'
down_revision: str | None = '0008'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'raw_pull',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('source_id', sa.String(32), nullable=False),
        sa.Column('pulled_on', sa.Date(), nullable=False),
        sa.Column('pulled_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('projects', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('payload', sa.JSON(), nullable=False, server_default='{}'),
        sa.UniqueConstraint('source_id', 'pulled_on'),
        schema='app',
    )
    op.create_index('ix_app_raw_pull_source_id', 'raw_pull', ['source_id'], schema='app')
    op.create_index('ix_app_raw_pull_pulled_on', 'raw_pull', ['pulled_on'], schema='app')


def downgrade() -> None:
    op.drop_index('ix_app_raw_pull_pulled_on', table_name='raw_pull', schema='app')
    op.drop_index('ix_app_raw_pull_source_id', table_name='raw_pull', schema='app')
    op.drop_table('raw_pull', schema='app')
