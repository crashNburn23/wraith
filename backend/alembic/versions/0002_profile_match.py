"""Add user_profile table and profile_match scoring columns

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-07
"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # New user_profile table
    op.create_table(
        "user_profile",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("sectors", sa.JSON, nullable=True),
        sa.Column("threat_actors", sa.JSON, nullable=True),
        sa.Column("categories", sa.JSON, nullable=True),
        sa.Column("keywords", sa.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    # Seed the single profile row
    op.execute("INSERT INTO user_profile (id, sectors, threat_actors, categories, keywords) VALUES (1, '[]', '[]', '[]', '[]')")

    # New scoring_config column
    op.add_column("scoring_config", sa.Column("weight_profile_match", sa.Float, server_default="0.25", nullable=False))

    # Rebalance existing scoring_config row to new defaults
    op.execute("""
        UPDATE scoring_config SET
            weight_ai_severity    = 0.35,
            weight_feedback_signal = 0.20,
            weight_profile_match  = 0.25,
            weight_kev_bonus      = 0.10,
            weight_recency        = 0.10
    """)

    # New bulletin_items columns
    op.add_column("bulletin_items", sa.Column("score_profile_match", sa.Float, server_default="0.0", nullable=False))
    op.add_column("bulletin_items", sa.Column("raw_profile_match",   sa.Float, server_default="0.0", nullable=False))


def downgrade() -> None:
    op.drop_column("bulletin_items", "raw_profile_match")
    op.drop_column("bulletin_items", "score_profile_match")
    op.drop_column("scoring_config", "weight_profile_match")
    op.drop_table("user_profile")
