import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from common.models.base import Base


class AgentStatus(str, enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    UNKNOWN = "unknown"


class Agent(Base):
    """
    Represents a sentinel-agent daemon registered in the system.

    Agents are identified by a unique ``agent_id`` (defaults to hostname).
    The conductor distributes its RSA public key; agents store it locally.
    """

    __tablename__ = "agents"

    agent_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hostname: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[AgentStatus] = mapped_column(
        Enum(AgentStatus, values_callable=lambda x: [e.value for e in x]),
        default=AgentStatus.UNKNOWN,
        nullable=False,
    )
    last_heartbeat: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Labels stored as JSON string for simple querying without JSON column type
    labels_json: Mapped[str | None] = mapped_column(Text, nullable=True, default="{}")

    # Relationships
    group_memberships: Mapped[list["AgentGroupMembership"]] = relationship(  # noqa: F821
        "AgentGroupMembership", back_populates="agent", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Agent id={self.agent_id!r} status={self.status}>"
