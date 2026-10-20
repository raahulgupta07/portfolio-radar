"""program office data: programs (charter, budget, team) and their projects

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-20 13:00:00
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '0007'
down_revision: str | None = '0006'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'po_program',
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('name', sa.String(200), nullable=False, server_default=''),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('data', sa.JSON(), nullable=False, server_default='{}'),
        sa.Column('imported_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema='app',
    )
    op.create_table(
        'po_project',
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('program_id', sa.String(64), nullable=False, server_default=''),
        sa.Column('name', sa.String(300), nullable=False, server_default=''),
        sa.Column('data', sa.JSON(), nullable=False, server_default='{}'),
        sa.Column('imported_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema='app',
    )
    op.create_index('ix_app_po_project_program_id', 'po_project', ['program_id'], schema='app')


def downgrade() -> None:
    op.drop_index('ix_app_po_project_program_id', table_name='po_project', schema='app')
    op.drop_table('po_project', schema='app')
    op.drop_table('po_program', schema='app')
