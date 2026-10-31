"""Persistent employer discovery registry.

Revision ID: 0003
Revises: 0002
"""
import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    if "employer_catalogs" not in sa.inspect(op.get_bind()).get_table_names():
        op.create_table("employer_catalogs",
            sa.Column("id", sa.String(80), primary_key=True),
            sa.Column("title", sa.String(200), nullable=False),
            sa.Column("url", sa.String(1000), nullable=False),
            sa.Column("status", sa.String(32), nullable=False),
            sa.Column("checked_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("source_id", sa.String(80), sa.ForeignKey("sources.id"), nullable=True, unique=True))
    if "employers" not in sa.inspect(op.get_bind()).get_table_names():
        op.create_table("employers",
            sa.Column("id", sa.String(96), primary_key=True),
            sa.Column("name", sa.String(200), nullable=False),
            sa.Column("name_key", sa.String(220), nullable=False, unique=True),
            sa.Column("profile", sa.JSON(), nullable=False),
            sa.Column("references", sa.JSON(), nullable=False),
            sa.Column("careers_url", sa.String(1000), nullable=True),
            sa.Column("manual", sa.Boolean(), nullable=False),
            sa.Column("active", sa.Boolean(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False))
        op.create_index("ix_employers_active", "employers", ["active"])


def downgrade():
    op.drop_index("ix_employers_active", table_name="employers")
    op.drop_table("employers")
    op.drop_table("employer_catalogs")
