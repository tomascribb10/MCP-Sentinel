from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from common.models.base import Base


class HostGroup(Base):
    """
    A logical group of sentinel-agents (e.g. 'prod_web_servers').

    Used as the target scope in RoleBinding policies.
    Labels are stored as a JSON string for portability across DB engines.
    """

    __tablename__ = "host_groups"

    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    labels_json: Mapped[str | None] = mapped_column(Text, nullable=True, default="{}")

    memberships: Mapped[list["AgentGroupMembership"]] = relationship(
        "AgentGroupMembership", back_populates="group", cascade="all, delete-orphan"
    )
    role_bindings: Mapped[list["RoleBinding"]] = relationship(  # noqa: F821
        "RoleBinding", back_populates="target_group"
    )

    def __repr__(self) -> str:
        return f"<HostGroup name={self.name!r}>"


class AgentGroupMembership(Base):
    """Association table linking agents to host groups."""

    __tablename__ = "agent_group_memberships"

    agent_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    group_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("host_groups.id", ondelete="CASCADE"), nullable=False, index=True
    )

    agent: Mapped["Agent"] = relationship("Agent", back_populates="group_memberships")  # noqa: F821
    group: Mapped["HostGroup"] = relationship("HostGroup", back_populates="memberships")
