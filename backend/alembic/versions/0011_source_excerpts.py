"""Add source_excerpt to entity tables for AI provenance.

Revision ID: 0011
Revises: 0010
Create Date: 2026-06-13
"""
from alembic import op
import sqlalchemy as sa

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("iocs",          sa.Column("source_excerpt", sa.Text, nullable=True))
    op.add_column("ttp_tags",      sa.Column("source_excerpt", sa.Text, nullable=True))
    op.add_column("article_actors", sa.Column("source_excerpt", sa.Text, nullable=True))
    op.add_column("cve_mentions",  sa.Column("source_excerpt", sa.Text, nullable=True))


def downgrade() -> None:
    op.drop_column("cve_mentions",   "source_excerpt")
    op.drop_column("article_actors", "source_excerpt")
    op.drop_column("ttp_tags",       "source_excerpt")
    op.drop_column("iocs",           "source_excerpt")
