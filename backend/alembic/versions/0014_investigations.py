"""Add investigation workspace tables."""
from alembic import op
import sqlalchemy as sa

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "investigations",
        sa.Column("id",          sa.String(36),  primary_key=True),
        sa.Column("name",        sa.String(200), nullable=False),
        sa.Column("description", sa.Text,        nullable=True),
        sa.Column("status",      sa.String(20),  nullable=False, server_default="open"),
        sa.Column("created_at",  sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at",  sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "investigation_articles",
        sa.Column("id",               sa.String(36), primary_key=True),
        sa.Column("investigation_id", sa.String(36), sa.ForeignKey("investigations.id"), nullable=False),
        sa.Column("article_id",       sa.String(36), sa.ForeignKey("articles.id"),       nullable=False),
        sa.Column("note",             sa.Text,       nullable=True),
        sa.Column("created_at",       sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at",       sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "investigation_notes",
        sa.Column("id",               sa.String(36), primary_key=True),
        sa.Column("investigation_id", sa.String(36), sa.ForeignKey("investigations.id"), nullable=False),
        sa.Column("content",          sa.Text,       nullable=False),
        sa.Column("created_at",       sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at",       sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("investigation_notes")
    op.drop_table("investigation_articles")
    op.drop_table("investigations")
