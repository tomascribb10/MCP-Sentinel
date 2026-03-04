from sqlalchemy import Boolean, ForeignKey, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from common.models.base import Base


class CommandSet(Base):
    """
    A named collection of allowed commands for a specific execution driver.

    Everything NOT listed in a CommandSet is implicitly denied (Default Deny).
    The ``driver`` field maps to a stevedore entry point in sentinel.agent.drivers.
    """

    __tablename__ = "command_sets"

    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    driver: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Stevedore driver name, e.g. 'posix_bash', 'openstack_sdk'",
    )

    commands: Mapped[list["Command"]] = relationship(
        "Command", back_populates="command_set", cascade="all, delete-orphan"
    )
    role_bindings: Mapped[list["RoleBinding"]] = relationship(
        "RoleBinding", back_populates="command_set"
    )

    def __repr__(self) -> str:
        return f"<CommandSet name={self.name!r} driver={self.driver!r}>"


class Command(Base):
    """
    A single allowed command within a CommandSet.

    ``binary`` is the full path to the executable.
    ``args_regex`` is a whitelist regex for the argument string.
    ``require_2fa`` triggers the 2FA flow in sentinel-conductor before signing.
    """

    __tablename__ = "commands"

    command_set_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("command_sets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    binary: Mapped[str] = mapped_column(String(512), nullable=False)
    args_regex: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Whitelist regex applied to the full argument string",
    )
    require_2fa: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    require_sudo: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        comment="If True, the driver prepends /usr/bin/sudo before executing.",
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    allowed_paths: Mapped[list[str] | None] = mapped_column(
        JSON,
        nullable=True,
        default=None,
        comment="Optional list of allowed filesystem path prefixes (e.g. ['/var/log/']). "
                "If set, any path-like argument must start with one of these prefixes.",
    )

    command_set: Mapped["CommandSet"] = relationship("CommandSet", back_populates="commands")

    def __repr__(self) -> str:
        return f"<Command name={self.name!r} binary={self.binary!r} 2fa={self.require_2fa}>"


class RoleBinding(Base):
    """
    Binds a principal (AI agent / LLM identity) to a CommandSet on a HostGroup.

    This is the core RBAC policy record.  The Conductor evaluates all three
    conditions before authorising an execution request:
      1. Does the target agent belong to ``target_group``?
      2. Is the requested command listed in ``command_set``?
      3. Does the args string match the command's ``args_regex``?
    """

    __tablename__ = "role_bindings"

    # The identity making the request (e.g. "llm-agent-claude", "mcp-client-xyz")
    principal_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)

    command_set_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("command_sets.id", ondelete="CASCADE"), nullable=False
    )
    target_group_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("host_groups.id", ondelete="CASCADE"), nullable=False
    )

    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    command_set: Mapped["CommandSet"] = relationship(
        "CommandSet", back_populates="role_bindings"
    )
    target_group: Mapped["HostGroup"] = relationship(  # noqa: F821
        "HostGroup", back_populates="role_bindings"
    )

    def __repr__(self) -> str:
        return (
            f"<RoleBinding principal={self.principal_id!r} "
            f"command_set={self.command_set_id!r}>"
        )
