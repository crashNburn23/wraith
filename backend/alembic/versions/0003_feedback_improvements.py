"""Feedback upsert constraint + decay config

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-08
"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Deduplicate feedback — keep the most recently updated row per article.
    # The window-function query works on both SQLite and PostgreSQL.
    op.execute("""
        DELETE FROM feedback
        WHERE id IN (
            SELECT id
            FROM (
                SELECT
                    id,
                    ROW_NUMBER() OVER (
                        PARTITION BY article_id
                        ORDER BY updated_at DESC, created_at DESC, id DESC
                    ) AS duplicate_rank
                FROM feedback
            ) ranked
            WHERE duplicate_rank > 1
        )
    """)

    # 2. Add unique constraint on feedback.article_id (requires batch for SQLite)
    with op.batch_alter_table("feedback") as batch_op:
        batch_op.create_unique_constraint("uq_feedback_article_id", ["article_id"])

    # 3. Add feedback decay half-life to scoring_config
    op.add_column(
        "scoring_config",
        sa.Column("feedback_decay_half_life_days", sa.Float, server_default="30.0", nullable=False),
    )
    op.execute("UPDATE scoring_config SET feedback_decay_half_life_days = 30.0")


def downgrade() -> None:
    op.drop_column("scoring_config", "feedback_decay_half_life_days")
    with op.batch_alter_table("feedback") as batch_op:
        batch_op.drop_constraint("uq_feedback_article_id", type_="unique")
