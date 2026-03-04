"""add allowed_paths to commands table

Revision ID: 0003
Revises: 0002
Create Date: 2026-03-03 00:00:00.000000

Adds the allowed_paths JSON column to commands.
When set, any path-like argument must start with one of the listed
prefixes.  NULL means no path restriction (backwards compatible).
"""

from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "commands",
        sa.Column("allowed_paths", sa.JSON, nullable=True, comment="Allowed filesystem path prefixes"),
    )


def downgrade() -> None:
    op.drop_column("commands", "allowed_paths")
