"""
sentinel_conductor.auth.stub
==============================
StubAuthProvider — auto-approves 2FA challenges after a configurable delay.

Stevedore entry point: ``stub``

USE ONLY IN DEVELOPMENT / TESTING.  This provider bypasses real human
approval and is intentionally excluded from production configurations.
"""

import asyncio
import uuid

from sentinel_conductor.auth.base import (
    BaseAuthProvider,
    ChallengeContext,
    ChallengeResponse,
    ChallengeStatus,
)


class StubAuthProvider(BaseAuthProvider):
    """
    Development 2FA provider that auto-approves after ``auto_approve_delay_seconds``.

    Set ``auto_approve = false`` in tests that need to simulate rejection.
    """

    name = "stub"

    def __init__(self, auto_approve: bool = True, auto_approve_delay_seconds: float = 1.0, **kwargs):
        super().__init__(**kwargs)
        self._auto_approve = auto_approve
        self._delay = auto_approve_delay_seconds
        # In-memory store: challenge_id → ChallengeStatus
        self._challenges: dict[str, ChallengeStatus] = {}

    async def issue_challenge(self, context: ChallengeContext) -> ChallengeResponse:
        challenge_id = str(uuid.uuid4())
        self._challenges[challenge_id] = ChallengeStatus.PENDING

        if self._auto_approve:
            asyncio.get_event_loop().call_later(
                self._delay,
                lambda: self._challenges.update({challenge_id: ChallengeStatus.APPROVED}),
            )

        return ChallengeResponse(
            challenge_id=challenge_id,
            status=ChallengeStatus.PENDING,
            external_ref=f"stub:{challenge_id}",
        )

    async def verify_challenge(
        self, challenge_id: str, external_ref: str | None
    ) -> ChallengeResponse:
        status = self._challenges.get(challenge_id, ChallengeStatus.EXPIRED)
        return ChallengeResponse(
            challenge_id=challenge_id,
            status=status,
            external_ref=external_ref,
        )
