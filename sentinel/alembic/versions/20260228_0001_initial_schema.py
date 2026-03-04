"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-02-28 00:00:00.000000

Creates all MCP-Sentinel tables:
  - agents
  - host_groups
  - agent_group_memberships
  - command_sets
  - commands
  - role_bindings
  - audit_logs
  - users
  - twofa_challenges
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # agents
    # ------------------------------------------------------------------
    op.create_table(
        "agents",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("agent_id", sa.String(255), nullable=False),
        sa.Column("hostname", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column(
            "status",
            sa.Enum("active", "inactive", "unknown", name="agentstatus"),
            nullable=False,
            server_default="unknown",
        ),
        sa.Column("last_heartbeat", sa.DateTime(timezone=True), nullable=True),
        sa.Column("labels_json", sa.Text, nullable=True, server_default="{}"),
    )
    op.create_index("ix_agents_agent_id", "agents", ["agent_id"], unique=True)

    # ------------------------------------------------------------------
    # host_groups
    # ------------------------------------------------------------------
    op.create_table(
        "host_groups",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("labels_json", sa.Text, nullable=True, server_default="{}"),
    )
    op.create_index("ix_host_groups_name", "host_groups", ["name"], unique=True)

    # ------------------------------------------------------------------
    # agent_group_memberships
    # ------------------------------------------------------------------
    op.create_table(
        "agent_group_memberships",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "agent_id",
            sa.String(36),
            sa.ForeignKey("agents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "group_id",
            sa.String(36),
            sa.ForeignKey("host_groups.id", ondelete="CASCADE"),
            nullable=False,
        ),
    )
    op.create_index("ix_agm_agent_id", "agent_group_memberships", ["agent_id"])
    op.create_index("ix_agm_group_id", "agent_group_memberships", ["group_id"])

    # ------------------------------------------------------------------
    # command_sets
    # ------------------------------------------------------------------
    op.create_table(
        "command_sets",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("driver", sa.String(100), nullable=False),
    )
    op.create_index("ix_command_sets_name", "command_sets", ["name"], unique=True)

    # ------------------------------------------------------------------
    # commands
    # ------------------------------------------------------------------
    op.create_table(
        "commands",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "command_set_id",
            sa.String(36),
            sa.ForeignKey("command_sets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("binary", sa.String(512), nullable=False),
        sa.Column("args_regex", sa.Text, nullable=True),
        sa.Column("require_2fa", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("description", sa.Text, nullable=True),
    )
    op.create_index("ix_commands_command_set_id", "commands", ["command_set_id"])

    # ------------------------------------------------------------------
    # role_bindings
    # ------------------------------------------------------------------
    op.create_table(
        "role_bindings",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("principal_id", sa.String(255), nullable=False),
        sa.Column(
            "command_set_id",
            sa.String(36),
            sa.ForeignKey("command_sets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "target_group_id",
            sa.String(36),
            sa.ForeignKey("host_groups.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default="true"),
    )
    op.create_index("ix_role_bindings_principal_id", "role_bindings", ["principal_id"])

    # ------------------------------------------------------------------
    # audit_logs
    # ------------------------------------------------------------------
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "type_uri",
            sa.String(255),
            nullable=False,
            server_default="activity/sentinel/execution",
        ),
        sa.Column("event_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("initiator_id", sa.String(255), nullable=False),
        sa.Column("initiator_type", sa.String(50), nullable=False, server_default="llm-agent"),
        sa.Column("action", sa.String(255), nullable=False),
        sa.Column("target_agent_id", sa.String(255), nullable=True),
        sa.Column("target_host", sa.String(255), nullable=True),
        sa.Column("driver", sa.String(100), nullable=True),
        sa.Column("binary", sa.String(512), nullable=True),
        sa.Column("args", sa.Text, nullable=True),
        sa.Column(
            "outcome",
            sa.Enum("success", "failure", "pending", "denied", name="auditoutcome"),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("reason", sa.Text, nullable=True),
        sa.Column("twofa_required", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("twofa_provider", sa.String(50), nullable=True),
        sa.Column("twofa_challenge_id", sa.String(36), nullable=True),
        sa.Column("message_id", sa.String(36), nullable=False),
        sa.Column("request_id", sa.String(36), nullable=True),
    )
    op.create_index("ix_audit_logs_event_time", "audit_logs", ["event_time"])
    op.create_index("ix_audit_logs_initiator_id", "audit_logs", ["initiator_id"])
    op.create_index("ix_audit_logs_target_agent_id", "audit_logs", ["target_agent_id"])
    op.create_index("ix_audit_logs_outcome", "audit_logs", ["outcome"])
    op.create_index("ix_audit_logs_message_id", "audit_logs", ["message_id"])
    op.create_index("ix_audit_logs_request_id", "audit_logs", ["request_id"])

    # ------------------------------------------------------------------
    # users  (standalone Admin API auth)
    # ------------------------------------------------------------------
    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("username", sa.String(150), nullable=False),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("is_superuser", sa.Boolean, nullable=False, server_default="false"),
    )
    op.create_index("ix_users_username", "users", ["username"], unique=True)
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    # ------------------------------------------------------------------
    # twofa_challenges
    # ------------------------------------------------------------------
    op.create_table(
        "twofa_challenges",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "audit_log_id",
            sa.String(36),
            sa.ForeignKey("audit_logs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column(
            "status",
            sa.Enum("pending", "approved", "rejected", "expired", name="challengestatus"),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("context_json", sa.Text, nullable=True),
        sa.Column("external_ref", sa.String(255), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_twofa_challenges_audit_log_id", "twofa_challenges", ["audit_log_id"])
    op.create_index("ix_twofa_challenges_status", "twofa_challenges", ["status"])


def downgrade() -> None:
    op.drop_table("twofa_challenges")
    op.drop_table("users")
    op.drop_table("audit_logs")
    op.drop_table("role_bindings")
    op.drop_table("commands")
    op.drop_table("command_sets")
    op.drop_table("agent_group_memberships")
    op.drop_table("host_groups")
    op.drop_table("agents")

    # Drop PostgreSQL enum types
    op.execute("DROP TYPE IF EXISTS challengestatus")
    op.execute("DROP TYPE IF EXISTS auditoutcome")
    op.execute("DROP TYPE IF EXISTS agentstatus")
