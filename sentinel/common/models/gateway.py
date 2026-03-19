import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from common.models.base import Base


class GatewayStatus(str, enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    UNKNOWN = "unknown"


class Gateway(Base):
    """
    Represents a sentinel-target running in gateway mode.

    A gateway manages remote targets (e.g. switches, appliances) that
    cannot run a sentinel-target process directly. It registers on behalf
    of its managed targets and proxies execution payloads to them.
    """

    __tablename__ = "gateways"

    gateway_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hostname: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[GatewayStatus] = mapped_column(
        Enum(GatewayStatus, values_callable=lambda x: [e.value for e in x]),
        default=GatewayStatus.UNKNOWN,
        nullable=False,
    )
    last_heartbeat: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    labels_json: Mapped[str | None] = mapped_column(Text, nullable=True, default="{}")

    targets: Mapped[list["Target"]] = relationship(  # noqa: F821
        "Target", back_populates="gateway", foreign_keys="Target.gateway_id"
    )

    def __repr__(self) -> str:
        return f"<Gateway id={self.gateway_id!r} status={self.status}>"
