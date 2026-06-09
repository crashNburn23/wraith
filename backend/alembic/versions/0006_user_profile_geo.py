"""Add geo_targets and geo_origins to user_profile

Revision ID: 0006
Revises: 0005
Create Date: 2026-06-09
"""
from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("user_profile", sa.Column("geo_targets", sa.JSON, nullable=True))
    op.add_column("user_profile", sa.Column("geo_origins", sa.JSON, nullable=True))


def downgrade() -> None:
    op.drop_column("user_profile", "geo_origins")
    op.drop_column("user_profile", "geo_targets")
