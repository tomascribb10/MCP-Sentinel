"""
sentinel_target.crypto
======================
Payload verification for sentinel-target.

The target NEVER signs — it only verifies.

**Golden Rule:** Every payload received from RabbitMQ MUST pass
``PayloadVerifier.verify()`` before any execution takes place.
Failed verification → log SECURITY ALERT + discard (never execute).
"""

import logging
import time

from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey

from common.crypto import load_public_key, verify_payload_signature
from common.exceptions import PayloadTampered, SignatureVerificationFailed

LOG = logging.getLogger(__name__)

# Payloads older than this are rejected as potential replays.
MAX_PAYLOAD_AGE_SECONDS = 120
# Reject payloads with timestamps this far in the future (clock skew protection).
MAX_FUTURE_SKEW_SECONDS = 30


class PayloadVerifier:
    """
    Holds the conductor's public key and exposes a single ``verify()`` method.

    Instantiate once at target startup via ``from_config()``, then call
    ``verify(payload_dict)`` on every incoming message.
    """

    def __init__(
        self,
        public_key: RSAPublicKey,
        max_age_seconds: int = MAX_PAYLOAD_AGE_SECONDS,
    ):
        self._public_key = public_key
        self._max_age = max_age_seconds

    @classmethod
    def from_config(cls, conf) -> "PayloadVerifier":
        """Load the conductor's public key using the oslo.config path."""
        key_path = conf.target.conductor_public_key_path
        LOG.info("Loading conductor public key from %s", key_path)
        public_key = load_public_key(key_path)
        return cls(public_key)

    def verify(self, payload_dict: dict) -> None:
        """
        Full payload verification:
          1. RSA-SHA256 signature check.
          2. Timestamp freshness (replay-attack protection).

        Raises:
            SignatureVerificationFailed: invalid or missing signature.
            PayloadTampered: timestamp too old or too far in the future.
        """
        message_id = payload_dict.get("message_id", "unknown")

        # --- 1. Cryptographic check ---
        try:
            verify_payload_signature(payload_dict, self._public_key)
        except SignatureVerificationFailed:
            LOG.critical(
                "SECURITY ALERT: Signature FAILED for message_id=%s — discarding.",
                message_id,
            )
            raise

        # --- 2. Replay protection ---
        try:
            payload_ts = int(payload_dict["security"]["timestamp"])
        except (KeyError, ValueError, TypeError) as exc:
            raise SignatureVerificationFailed(
                "Payload is missing a valid security.timestamp."
            ) from exc

        now = int(time.time())
        age = now - payload_ts

        if age > self._max_age:
            raise PayloadTampered(
                f"Payload is {age}s old (max {self._max_age}s). "
                "Possible replay attack — discarding."
            )
        if age < -MAX_FUTURE_SKEW_SECONDS:
            raise PayloadTampered(
                f"Payload timestamp is {-age}s in the future. "
                "Possible clock skew or replay attack — discarding."
            )

        LOG.debug("Payload OK: message_id=%s age=%ds", message_id, age)
