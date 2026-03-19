import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from common.models.base import Base


class TargetStatus(str, enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    UNKNOWN = "unknown"


class TargetType(str, enum.Enum):
    DIRECT = "direct"
    GATEWAY_MANAGED = "gateway_managed"


class Target(Base):
    """
    Represents a sentinel-target registered in the system.

    Targets are identified by a unique ``target_id`` (defaults to hostname).

    - ``direct`` targets run sentinel-target locally and execute commands
      themselves.
    - ``gateway_managed`` targets are remote devices (e.g. switches) that
      cannot run sentinel. A Gateway registers them and proxies execution.
    """

    __tablename__ = "targets"

    target_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hostname: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_type: Mapped[TargetType] = mapped_column(
        Enum(TargetType, values_callable=lambda x: [e.value for e in x]),
        default=TargetType.DIRECT,
        nullable=False,
    )
    gateway_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("gateways.id", ondelete="SET NULL"), nullable=True, index=True
    )
    status: Mapped[TargetStatus] = mapped_column(
        Enum(TargetStatus, values_callable=lambda x: [e.value for e in x]),
        default=TargetStatus.UNKNOWN,
        nullable=False,
    )
    last_heartbeat: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    labels_json: Mapped[str | None] = mapped_column(Text, nullable=True, default="{}")

    group_memberships: Mapped[list["TargetGroupMembership"]] = relationship(  # noqa: F821
        "TargetGroupMembership", back_populates="target", cascade="all, delete-orphan"
    )
    gateway: Mapped["Gateway | None"] = relationship(  # noqa: F821
        "Gateway", back_populates="targets", foreign_keys=[gateway_id]
    )

    def __repr__(self) -> str:
        return f"<Target id={self.target_id!r} type={self.target_type} status={self.status}>"
