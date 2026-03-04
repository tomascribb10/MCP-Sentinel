"""
Auth models — standalone mode (no Keystone).

``User``          — Admin API local user account.
``TwoFAChallenge`` — Tracks in-flight 2FA challenges issued by the conductor.
"""

import enum

from sqlalchemy import Boolean, Enum, ForeignKey, String, Text, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from common.models.base import Base, _utcnow
from datetime import datetime


class User(Base):
    """Local admin user for the sentinel-admin-api (standalone mode)."""

    __tablename__ = "users"

    username: Mapped[str] = mapped_column(String(150), unique=True, nullable=False, index=True)
    email: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    def __repr__(self) -> str:
        return f"<User username={self.username!r} superuser={self.is_superuser}>"


class ChallengeStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class TwoFAChallenge(Base):
    """
    Tracks an in-flight 2FA challenge.

    The conductor creates a challenge record, sends the push notification
    via the configured provider plugin, and then polls / awaits callback
    to update the status.  The RBAC engine blocks dispatch until the
    challenge reaches APPROVED status or the timeout is exceeded.
    """

    __tablename__ = "twofa_challenges"

    # Which audit log event this challenge belongs to
    audit_log_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("audit_logs.id", ondelete="SET NULL"), nullable=True, index=True
    )

    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[ChallengeStatus] = mapped_column(
        Enum(ChallengeStatus, values_callable=lambda x: [e.value for e in x]),
        default=ChallengeStatus.PENDING,
        nullable=False,
        index=True,
    )

    # Human-readable context sent in the 2FA push message
    context_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Provider-specific external reference (e.g. Telegram message_id)
    external_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)

    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    def __repr__(self) -> str:
        return f"<TwoFAChallenge id={self.id!r} status={self.status}>"
