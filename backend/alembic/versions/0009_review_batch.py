"""Review batch: job state persistence, corrections memory, watchlist,
article embeddings, CVE plain-English summaries.

Revision ID: 0009
Revises: 0008
Create Date: 2026-06-10
"""
from alembic import op
import sqlalchemy as sa

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "job_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("job_type", sa.String(20), nullable=False, index=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("payload", sa.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "job_flags",
        sa.Column("job_type", sa.String(20), primary_key=True),
        sa.Column("paused", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("stopped", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "enrichment_corrections",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("entity_type", sa.String(20), nullable=False),
        sa.Column("action", sa.String(20), nullable=False),
        sa.Column("original_value", sa.Text, nullable=False),
        sa.Column("corrected_value", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "watchlist_items",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("item_type", sa.String(20), nullable=False),
        sa.Column("value", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.add_column("articles", sa.Column("embedding", sa.JSON, nullable=True))
    op.add_column("cve_records", sa.Column("ai_summary", sa.Text, nullable=True))


def downgrade() -> None:
    op.drop_column("cve_records", "ai_summary")
    op.drop_column("articles", "embedding")
    op.drop_table("watchlist_items")
    op.drop_table("enrichment_corrections")
    op.drop_table("job_flags")
    op.drop_table("job_runs")
