"""Add brief columns to bulletins

Revision ID: 0007
Revises: 0006
Create Date: 2026-06-09
"""
from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("bulletins", sa.Column("brief", sa.Text, nullable=True))
    op.add_column("bulletins", sa.Column("brief_generated_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("bulletins", "brief_generated_at")
    op.drop_column("bulletins", "brief")
