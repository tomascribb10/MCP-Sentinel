"""
Audit log model — CADF-inspired format.

CADF (Cloud Audit Data Federation) defines:
  - typeURI, id, eventTime
  - initiator  (who triggered the action)
  - action     (what was requested)
  - target     (the resource acted upon)
  - outcome    (success / failure / pending)
  - observer   (sentinel-conductor)

These records are IMMUTABLE once written. The ORM model intentionally
omits ``updated_at`` from Base — we override it here.
"""

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from common.models.base import Base


class AuditOutcome(str, enum.Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    PENDING = "pending"
    DENIED = "denied"


class AuditLog(Base):
    """
    Immutable CADF-inspired audit record.

    One record is created per execution request lifecycle event
    (requested, 2fa_pending, 2fa_approved, dispatched, completed, failed).
    """

    __tablename__ = "audit_logs"

    # CADF fields
    type_uri: Mapped[str] = mapped_column(
        String(255),
        default="activity/sentinel/execution",
        nullable=False,
    )
    event_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )

    # Initiator — who made the request
    initiator_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    initiator_type: Mapped[str] = mapped_column(
        String(50), default="llm-agent", nullable=False
    )

    # Action — what was requested
    action: Mapped[str] = mapped_column(String(255), nullable=False)

    # Target — where it was executed
    target_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    target_host: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Execution detail
    driver: Mapped[str | None] = mapped_column(String(100), nullable=True)
    binary: Mapped[str | None] = mapped_column(String(512), nullable=True)
    args: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Outcome
    outcome: Mapped[AuditOutcome] = mapped_column(
        Enum(AuditOutcome, values_callable=lambda x: [e.value for e in x]),
        default=AuditOutcome.PENDING,
        nullable=False,
        index=True,
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # 2FA tracking
    twofa_required: Mapped[bool] = mapped_column(default=False, nullable=False)
    twofa_provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    twofa_challenge_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    # Execution output (populated by report_execution_result from the target)
    stdout: Mapped[str | None] = mapped_column(Text, nullable=True)
    stderr: Mapped[str | None] = mapped_column(Text, nullable=True)
    exit_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Correlation
    message_id: Mapped[str] = mapped_column(
        String(36), default=lambda: str(uuid.uuid4()), nullable=False, index=True
    )
    request_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)

    def __repr__(self) -> str:
        return (
            f"<AuditLog id={self.id!r} action={self.action!r} outcome={self.outcome}>"
        )
