"""add require_sudo to commands table

Revision ID: 0004
Revises: 0003
Create Date: 2026-03-04 00:00:00.000000

Adds require_sudo boolean column to commands.
When True, sentinel-agent prepends /usr/bin/sudo to the command invocation.
Defaults to False (backwards compatible — existing commands are unchanged).
"""

from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "commands",
        sa.Column(
            "require_sudo",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
            comment="If true, the agent driver prepends /usr/bin/sudo to the command.",
        ),
    )


def downgrade() -> None:
    op.drop_column("commands", "require_sudo")
