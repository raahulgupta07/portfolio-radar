"""program office change history

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-20 15:00:00
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '0008'
down_revision: str | None = '0007'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'po_activity',
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('at', sa.String(40), nullable=False, server_default=''),
        sa.Column('by', sa.String(200), nullable=False, server_default=''),
        sa.Column('kind', sa.String(16), nullable=False, server_default='project'),
        sa.Column('ref_id', sa.String(64), nullable=False, server_default=''),
        sa.Column('ref_name', sa.String(300), nullable=False, server_default=''),
        sa.Column('type', sa.String(16), nullable=False, server_default='updated'),
        sa.Column('changes', sa.JSON(), nullable=False, server_default='[]'),
        schema='app',
    )
    op.create_index('ix_app_po_activity_at', 'po_activity', ['at'], schema='app')


def downgrade() -> None:
    op.drop_index('ix_app_po_activity_at', table_name='po_activity', schema='app')
    op.drop_table('po_activity', schema='app')
