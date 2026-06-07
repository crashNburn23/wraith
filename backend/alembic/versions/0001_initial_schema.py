"""Initial schema

Revision ID: 0001
Revises:
Create Date: 2026-06-07
"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sources",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("url", sa.Text, nullable=False, unique=True),
        sa.Column("source_type", sa.String(50), nullable=False, server_default="rss"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="1"),
        sa.Column("last_fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consecutive_failures", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "articles",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("source_id", sa.String(36), sa.ForeignKey("sources.id"), nullable=False),
        sa.Column("url", sa.Text, nullable=False),
        sa.Column("url_hash", sa.String(64), unique=True, nullable=False),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scraped_text", sa.Text, nullable=True),
        sa.Column("enrichment_status", sa.String(50), nullable=False, server_default="pending"),
        sa.Column("enriched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ai_summary", sa.Text, nullable=True),
        sa.Column("threat_category", sa.String(100), nullable=True),
        sa.Column("ai_severity_score", sa.Float, nullable=True),
        sa.Column("sector_targets", sa.JSON, nullable=True),
        sa.Column("geo_origin", sa.String(100), nullable=True),
        sa.Column("geo_targets", sa.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_articles_source_id", "articles", ["source_id"])
    op.create_index("ix_articles_enrichment_status", "articles", ["enrichment_status"])
    op.create_index("ix_articles_published_at", "articles", ["published_at"])

    op.create_table(
        "threat_actors",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False, unique=True),
        sa.Column("aliases", sa.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "iocs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("article_id", sa.String(36), sa.ForeignKey("articles.id"), nullable=False),
        sa.Column("ioc_type", sa.String(50), nullable=False),
        sa.Column("value", sa.Text, nullable=False),
        sa.Column("user_note", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_iocs_article_id", "iocs", ["article_id"])
    op.create_index("ix_iocs_ioc_type", "iocs", ["ioc_type"])

    op.create_table(
        "ttp_tags",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("article_id", sa.String(36), sa.ForeignKey("articles.id"), nullable=False),
        sa.Column("technique_id", sa.String(20), nullable=False),
        sa.Column("technique_name", sa.String(255), nullable=False),
        sa.Column("tactic", sa.String(100), nullable=True),
        sa.Column("user_note", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_ttp_tags_article_id", "ttp_tags", ["article_id"])

    op.create_table(
        "article_actors",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("article_id", sa.String(36), sa.ForeignKey("articles.id"), nullable=False),
        sa.Column("actor_id", sa.String(36), sa.ForeignKey("threat_actors.id"), nullable=False),
        sa.Column("user_note", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_article_actors_article_id", "article_actors", ["article_id"])

    op.create_table(
        "cve_records",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("cve_id", sa.String(20), unique=True, nullable=False),
        sa.Column("cvss_score", sa.Float, nullable=True),
        sa.Column("epss_score", sa.Float, nullable=True),
        sa.Column("epss_percentile", sa.Float, nullable=True),
        sa.Column("in_kev", sa.Boolean, nullable=False, server_default="0"),
        sa.Column("kev_due_date", sa.String(20), nullable=True),
        sa.Column("nvd_description", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "cve_mentions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("article_id", sa.String(36), sa.ForeignKey("articles.id"), nullable=False),
        sa.Column("cve_id", sa.String(20), nullable=False),
        sa.Column("user_note", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_cve_mentions_article_id", "cve_mentions", ["article_id"])
    op.create_index("ix_cve_mentions_cve_id", "cve_mentions", ["cve_id"])

    op.create_table(
        "bulletins",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("bulletin_date", sa.String(10), unique=True, nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "bulletin_items",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("bulletin_id", sa.String(36), sa.ForeignKey("bulletins.id"), nullable=False),
        sa.Column("article_id", sa.String(36), sa.ForeignKey("articles.id"), nullable=False),
        sa.Column("rank", sa.Integer, nullable=False),
        sa.Column("computed_score", sa.Float, nullable=False, server_default="0"),
        sa.Column("score_ai_severity", sa.Float, nullable=False, server_default="0"),
        sa.Column("score_feedback_signal", sa.Float, nullable=False, server_default="0"),
        sa.Column("score_kev_bonus", sa.Float, nullable=False, server_default="0"),
        sa.Column("score_recency", sa.Float, nullable=False, server_default="0"),
        sa.Column("raw_ai_severity", sa.Float, nullable=False, server_default="0"),
        sa.Column("raw_feedback_signal", sa.Float, nullable=False, server_default="0"),
        sa.Column("raw_kev_bonus", sa.Float, nullable=False, server_default="0"),
        sa.Column("raw_recency_factor", sa.Float, nullable=False, server_default="0"),
        sa.Column("feedback_signal_articles", sa.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_bulletin_items_bulletin_id", "bulletin_items", ["bulletin_id"])

    op.create_table(
        "feedback",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("article_id", sa.String(36), sa.ForeignKey("articles.id"), nullable=False),
        sa.Column("rating", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_feedback_article_id", "feedback", ["article_id"])

    op.create_table(
        "read_status",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("article_id", sa.String(36), sa.ForeignKey("articles.id"), unique=True, nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="unread"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "scoring_config",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("weight_ai_severity", sa.Float, nullable=False, server_default="0.45"),
        sa.Column("weight_feedback_signal", sa.Float, nullable=False, server_default="0.30"),
        sa.Column("weight_kev_bonus", sa.Float, nullable=False, server_default="0.15"),
        sa.Column("weight_recency", sa.Float, nullable=False, server_default="0.10"),
        sa.Column("feedback_lookback_days", sa.Integer, nullable=False, server_default="90"),
        sa.Column("recency_half_life_days", sa.Float, nullable=False, server_default="3.0"),
        sa.Column("min_feedback_articles", sa.Integer, nullable=False, server_default="3"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("scoring_config")
    op.drop_table("read_status")
    op.drop_table("feedback")
    op.drop_table("bulletin_items")
    op.drop_table("bulletins")
    op.drop_table("cve_mentions")
    op.drop_table("cve_records")
    op.drop_table("article_actors")
    op.drop_table("ttp_tags")
    op.drop_table("iocs")
    op.drop_table("threat_actors")
    op.drop_table("articles")
    op.drop_table("sources")
