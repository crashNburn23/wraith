"""Story clustering: add cluster_id, is_cluster_lead, cluster_size to bulletin_items.

Revision ID: 0010
Revises: 0009
Create Date: 2026-06-11
"""
from alembic import op
import sqlalchemy as sa

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("bulletin_items", sa.Column("cluster_id", sa.String(36), nullable=True))
    op.add_column("bulletin_items", sa.Column("is_cluster_lead", sa.Boolean, nullable=False, server_default=sa.true()))
    op.add_column("bulletin_items", sa.Column("cluster_size", sa.Integer, nullable=False, server_default="1"))


def downgrade() -> None:
    op.drop_column("bulletin_items", "cluster_size")
    op.drop_column("bulletin_items", "is_cluster_lead")
    op.drop_column("bulletin_items", "cluster_id")
