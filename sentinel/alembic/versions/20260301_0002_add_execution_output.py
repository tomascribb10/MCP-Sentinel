"""add execution output columns to audit_logs

Revision ID: 0002
Revises: 0001
Create Date: 2026-03-01 00:00:00.000000

Adds stdout, stderr, exit_code and duration_ms to audit_logs.
These are populated by sentinel-agent via the report_execution_result
RPC cast after a command completes.
"""

from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("audit_logs", sa.Column("stdout", sa.Text, nullable=True))
    op.add_column("audit_logs", sa.Column("stderr", sa.Text, nullable=True))
    op.add_column("audit_logs", sa.Column("exit_code", sa.Integer, nullable=True))
    op.add_column("audit_logs", sa.Column("duration_ms", sa.Integer, nullable=True))


def downgrade() -> None:
    op.drop_column("audit_logs", "duration_ms")
    op.drop_column("audit_logs", "exit_code")
    op.drop_column("audit_logs", "stderr")
    op.drop_column("audit_logs", "stdout")
