"""Add enrichment model/prompt/schema version fields to articles."""
from alembic import op
import sqlalchemy as sa

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("articles", sa.Column("enrichment_model", sa.String(200), nullable=True))
    op.add_column("articles", sa.Column("enrichment_prompt_version", sa.String(20), nullable=True))
    op.add_column("articles", sa.Column("enrichment_schema_version", sa.String(20), nullable=True))


def downgrade() -> None:
    op.drop_column("articles", "enrichment_schema_version")
    op.drop_column("articles", "enrichment_prompt_version")
    op.drop_column("articles", "enrichment_model")
