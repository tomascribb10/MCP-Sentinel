"""
sentinel_conductor.auth.base
=============================
Abstract base class for all 2FA provider plugins loaded via stevedore.

Stevedore namespace: ``sentinel.auth.providers``

Provider authors must subclass ``BaseAuthProvider`` and implement:
  - ``issue_challenge(context)``   — send the push notification to the human approver
  - ``verify_challenge(challenge_id)`` — check current status of an in-flight challenge

The conductor uses these in a non-blocking manner:
  1. Calls ``issue_challenge()`` → stores the returned challenge_id.
  2. Sets execution status to PENDING_2FA.
  3. Polls ``verify_challenge()`` in a background task (or receives a callback).
  4. On APPROVED → proceeds with RSA signing and dispatch.
  5. On REJECTED / EXPIRED → denies with audit log entry.
"""

import abc
import enum
from dataclasses import dataclass, field
from typing import Any


class ChallengeStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


@dataclass
class ChallengeContext:
    """Context passed to the 2FA provider when issuing a challenge."""

    initiator_id: str
    target_agent_id: str
    command: str
    args: list[str]
    request_id: str
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class ChallengeResponse:
    """Result of ``verify_challenge()``."""

    challenge_id: str
    status: ChallengeStatus
    external_ref: str | None = None  # Provider-specific reference (e.g. Telegram message_id)


class BaseAuthProvider(abc.ABC):
    """
    Abstract 2FA provider plugin.

    Implementations are stateless regarding challenge data — all persistent
    state is stored in the ``TwoFAChallenge`` DB table by the conductor.
    """

    #: Stevedore entry point name; override in subclasses.
    name: str = "base"

    def __init__(self, **kwargs):
        """Providers may receive kwargs from oslo.config. Call super().__init__(**kwargs)."""

    @abc.abstractmethod
    async def issue_challenge(self, context: ChallengeContext) -> ChallengeResponse:
        """
        Send a 2FA push notification to the configured approver.

        Must return immediately with a ``ChallengeResponse`` in PENDING status
        and a provider-specific ``external_ref`` for later polling.

        Raises:
            RuntimeError: if the notification cannot be delivered.
        """

    @abc.abstractmethod
    async def verify_challenge(self, challenge_id: str, external_ref: str | None) -> ChallengeResponse:
        """
        Poll the provider to determine the current status of a challenge.

        Returns the updated ``ChallengeResponse``.  The conductor calls
        this repeatedly (or via webhook) until the status is no longer PENDING.

        Raises:
            RuntimeError: if the provider cannot be reached.
        """
