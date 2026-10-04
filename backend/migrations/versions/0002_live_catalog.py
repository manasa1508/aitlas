"""Structured metadata and lifecycle for live jobs and models.

Revision ID: 0002
Revises: 0001
"""
import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("items")}
    if "details" not in columns:
        op.add_column("items", sa.Column("details", sa.JSON(), nullable=False, server_default="{}"))
    if "active" not in columns:
        op.add_column("items", sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()))
    if "last_seen_at" not in columns:
        op.add_column("items", sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True))
    indexes = {index["name"] for index in sa.inspect(bind).get_indexes("items")}
    if "ix_items_active" not in indexes:
        op.create_index("ix_items_active", "items", ["active"])


def downgrade():
    bind = op.get_bind()
    indexes = {index["name"] for index in sa.inspect(bind).get_indexes("items")}
    if "ix_items_active" in indexes:
        op.drop_index("ix_items_active", table_name="items")
    columns = {column["name"] for column in sa.inspect(bind).get_columns("items")}
    for name in ("last_seen_at", "active", "details"):
        if name in columns:
            op.drop_column("items", name)
