"""Add ioc_whitelist table

Revision ID: 0008
Revises: 0007
Create Date: 2026-06-09
"""
from alembic import op
import sqlalchemy as sa

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ioc_whitelist",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("value", sa.Text, nullable=False, unique=True),
        sa.Column("ioc_type", sa.String(50), nullable=False),
        sa.Column("note", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("ioc_whitelist")
