"""people (Admin → People) and longer client IDs for Keycloak

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-20 09:00:00
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '0006'
down_revision: str | None = '0005'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'person',
        sa.Column('id', sa.String(200), primary_key=True),
        sa.Column('name', sa.String(200), nullable=False, server_default=''),
        sa.Column('sso_roles', sa.JSON(), nullable=False, server_default='[]'),
        sa.Column('extra_roles', sa.JSON(), nullable=False, server_default='[]'),
        sa.Column('blocked', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('note', sa.String(300), nullable=False, server_default=''),
        sa.Column('first_seen', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_seen', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_by', sa.String(200), nullable=False, server_default=''),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema='mcp',
    )
    # Keycloak client IDs are names, not 36-character GUIDs.
    op.alter_column('agent', 'app_id', type_=sa.String(200), existing_type=sa.String(36), schema='mcp')


def downgrade() -> None:
    op.alter_column('agent', 'app_id', type_=sa.String(36), existing_type=sa.String(200), schema='mcp')
    op.drop_table('person', schema='mcp')
