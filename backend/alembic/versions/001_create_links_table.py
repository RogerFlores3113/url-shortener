"""create links table

Revision ID: 001
Revises:
Create Date: 2026-04-23
"""

revision = "001"
down_revision = None
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.create_table(
        "links",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String(255), nullable=False),
        sa.Column("short_code", sa.String(7), nullable=False),
        sa.Column("long_url", sa.String(2048), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_unique_constraint("uq_links_short_code", "links", ["short_code"])
    op.create_index("ix_links_user_id", "links", ["user_id"])
    op.create_index("ix_links_expires_at", "links", ["expires_at"])


def downgrade():
    op.drop_table("links")
