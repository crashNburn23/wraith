"""Add saved_searches table."""
from alembic import op
import sqlalchemy as sa

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "saved_searches",
        sa.Column("id",                  sa.String(36),   primary_key=True),
        sa.Column("name",                sa.String(200),  nullable=False),
        sa.Column("filters",             sa.JSON,         nullable=False, server_default="{}"),
        sa.Column("alert_enabled",       sa.Boolean,      nullable=False, server_default="0"),
        sa.Column("alert_severity_min",  sa.Float,        nullable=False, server_default="0"),
        sa.Column("last_alerted_at",     sa.DateTime(timezone=True), nullable=True),
        sa.Column("match_count",         sa.Integer,      nullable=False, server_default="0"),
        sa.Column("created_at",          sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at",          sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("saved_searches")
